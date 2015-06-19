from migen.fhdl.std import *

from bfs_interfaces import BFSApplyInterface, BFSScatterInterface, BFSMessage
from bfs_address import BFSAddressLayout

class BFSApply(Module):
	def __init__(self, addresslayout):
		nodeidsize = addresslayout.nodeidsize
		num_nodes_per_pe = addresslayout.num_nodes_per_pe

		# input Q interface
		self.apply_interface = BFSApplyInterface(nodeidsize)

		# scatter interface
		# send self.update message to all neighbors
		# message format (sending_node_id) (normally would be (sending_node_id, payload), but for BFS payload = sending_node_id)
		self.scatter_interface = BFSScatterInterface(nodeidsize)

		####

		# should pipeline advance?
		clock_enable = Signal()

		self.specials.mem = Memory(nodeidsize, num_nodes_per_pe, init=[0 for i in range(num_nodes_per_pe)])
		self.specials.rd_port = rd_port = self.mem.get_port(has_re=True)
		self.specials.wr_port = wr_port = self.mem.get_port(write_capable=True)

		# input handling
		self.comb += self.apply_interface.ack.eq(clock_enable)

		# computation stage 1

		# look up parent(dest_node_id) to see if already visited
		self.comb += rd_port.adr.eq(addresslayout.local_adr(self.apply_interface.msg.dest_id)), rd_port.re.eq(clock_enable)

		# detect termination (if all PEs receive 2 barriers in a row)
		self.inactive = Signal()
		prev_was_barrier = Signal()
		prev_prev_was_barrier = Signal()
		self.sync += If(self.apply_interface.valid & clock_enable, prev_was_barrier.eq(self.apply_interface.msg.barrier))
		self.sync += If(self.apply_interface.valid & clock_enable, prev_prev_was_barrier.eq(prev_was_barrier))
		self.comb += self.inactive.eq(prev_was_barrier & prev_prev_was_barrier)

		# registers to next stage
		dest_node_id2 = Signal(nodeidsize)
		parent2 = Signal(nodeidsize)
		valid2 = Signal()
		barrier2 = Signal()

		self.sync += If(clock_enable, 
			dest_node_id2.eq(self.apply_interface.msg.dest_id), 
			parent2.eq(self.apply_interface.msg.parent), 
			valid2.eq(self.apply_interface.valid & ~ self.apply_interface.msg.barrier), # valid2 used to determine if write in next stage, so don't set for barrier
			barrier2.eq(self.apply_interface.valid & self.apply_interface.msg.barrier)
		)

		# computation stage 2

		# count levels
		self.level = Signal(min=0, max=(num_nodes_per_pe*addresslayout.num_pe))
		self.sync += If(barrier2 & clock_enable, self.level.eq(self.level + 1))


		# find out if we have an update
		# assumes 0 is not a valid nodeID
		self.update = Signal()
		self.comb += self.update.eq(valid2 & (rd_port.dat_r == 0))

		# if yes write parent value
		self.comb += wr_port.adr.eq(addresslayout.local_adr(dest_node_id2)), wr_port.dat_w.eq(parent2), wr_port.we.eq(self.update)
		# TODO: if next msg or one after is for same node, will not see updated value b/c write not completed yet
		# not correctness issue, just wasted effort (will send out messages twice)

		# output handling
		# if self.update (= node hadn't been previously visited), scatter own id (= visit children)
		self.comb += self.scatter_interface.msg.eq(dest_node_id2), self.scatter_interface.valid.eq(self.update | barrier2), self.scatter_interface.barrier.eq(barrier2)

		# stall if we can't send message (advance if receiver ready, or no data available)
		self.comb += clock_enable.eq(self.scatter_interface.ack | (~self.update & ~barrier2))