from migen.fhdl.std import *
from migen.genlib.record import *
from migen.genlib.fifo import SyncFIFO

from bfs_interfaces import BFSApplyInterface, BFSScatterInterface, BFSMessage, node_mem_layout, payload_layout
from bfs_address import BFSAddressLayout

## for wrapping signals when multiplexing memory port

_memory_port_layout = [
	( "enable", 1 ),
	( "adr", "adrsize" ),
	( "re", 1 ),
	( "dat_r", "datasize" )
]

class BFSApplyKernel(Module):
	def __init__(self, addresslayout):
		nodeidsize = addresslayout.nodeidsize

		self.nodeid_in = Signal(nodeidsize)
		self.message_in = Record(set_layout_parameters(payload_layout, nodeidsize=nodeidsize))
		self.state_in = Record(set_layout_parameters(node_mem_layout, nodeidsize=nodeidsize))
		self.valid_in = Signal()
		self.barrier_in = Signal()

		self.state_out = Record(set_layout_parameters(node_mem_layout, nodeidsize=nodeidsize))
		self.state_update = Signal()
		self.message_out = Record(set_layout_parameters(payload_layout, nodeidsize=nodeidsize))
		self.message_valid = Signal()
		self.barrier_out = Signal()

		###

		# find out if we have an update
		# assumes 0 is not a valid nodeID
		# if we read 0, node did not have a parent yet, and we want to write one now.
		# some sanity checks for sending & receiving node not being 0
		self.comb+= self.state_out.parent.eq(self.message_in.parent),\
					self.state_update.eq(self.valid_in & (self.state_in.parent == 0) & (self.nodeid_in != 0) & (self.message_in.parent != 0)),\
					self.message_out.parent.eq(self.nodeid_in),\
					self.message_valid.eq(self.state_update & (self.nodeid_in != 0)),\
					self.barrier_out.eq(self.barrier_in)



class BFSApply(Module):
	def __init__(self, addresslayout):
		nodeidsize = addresslayout.nodeidsize
		num_nodes_per_pe = addresslayout.num_nodes_per_pe

		# input Q interface
		self.apply_interface = BFSApplyInterface(nodeidsize=nodeidsize)

		# scatter interface
		# send self.update message to all neighbors
		# message format (sending_node_id) (normally would be (sending_node_id, payload), 
		# but for BFS payload = sending_node_id)
		self.scatter_interface = BFSScatterInterface(nodeidsize=nodeidsize)

		####

		# should pipeline advance?
		clock_enable = Signal()

		# local node data storage
		self.specials.mem = Memory(nodeidsize, num_nodes_per_pe, init=[0 for i in range(num_nodes_per_pe)])
		self.specials.rd_port = rd_port = self.mem.get_port(has_re=True)
		self.specials.wr_port = wr_port = self.mem.get_port(write_capable=True)

		# multiplex read port
		# during computation, update locally; after computation, controller sends contents back to host
		self.extern_rd_port = Record(set_layout_parameters(_memory_port_layout, adrsize=flen(rd_port.adr), datasize=flen(rd_port.dat_r)))

		local_rd_port = Record(set_layout_parameters(_memory_port_layout, adrsize=flen(rd_port.adr), datasize=flen(rd_port.dat_r)))

		self.comb += If(self.extern_rd_port.enable, 
						rd_port.adr.eq(self.extern_rd_port.adr),
						rd_port.re.eq(self.extern_rd_port.re)
					 ).Else(
					 	rd_port.adr.eq(local_rd_port.adr),
					 	rd_port.re.eq(local_rd_port.re)
					 ), \
					 self.extern_rd_port.dat_r.eq(rd_port.dat_r), \
					 local_rd_port.dat_r.eq(rd_port.dat_r)

		# input handling
		self.comb += self.apply_interface.ack.eq(clock_enable)

		collision = Signal()

		# detect termination (if all PEs receive 2 barriers in a row)
		self.inactive = Signal()
		prev_was_barrier = Signal()
		prev_prev_was_barrier = Signal()
		self.sync += If(self.apply_interface.valid & clock_enable, prev_was_barrier.eq(self.apply_interface.msg.barrier))
		self.sync += If(self.apply_interface.valid & clock_enable, prev_prev_was_barrier.eq(prev_was_barrier))
		self.comb += self.inactive.eq(prev_was_barrier & prev_prev_was_barrier)

		# computation stage 1

		# rename some signals for easier reading, separate barrier and normal valid
		dest_node_id = Signal(nodeidsize)
		payload = Record(set_layout_parameters(payload_layout, nodeidsize=nodeidsize))
		valid = Signal()
		barrier = Signal()

		self.comb += dest_node_id.eq(self.apply_interface.msg.dest_id),\
					 payload.eq(self.apply_interface.msg.payload),\
					 valid.eq(self.apply_interface.valid & ~self.apply_interface.msg.barrier),\
					 barrier.eq(self.apply_interface.valid & self.apply_interface.msg.barrier)

		# look up parent(dest_node_id) to see if already visited
		self.comb += local_rd_port.adr.eq(addresslayout.local_adr(dest_node_id)),\
					 local_rd_port.re.eq(clock_enable)

		# registers to next stage
		dest_node_id2 = Signal(nodeidsize)
		payload2 = Record(set_layout_parameters(payload_layout, nodeidsize=nodeidsize))
		valid2 = Signal()
		barrier2 = Signal()

		self.sync += If(clock_enable, 
			dest_node_id2.eq(dest_node_id), 
			payload2.eq(payload), 
			valid2.eq(valid), # valid2 used to determine if write in next stage, so don't set for barrier
			barrier2.eq(barrier)
		).Elif(collision,
			valid2.eq(0)
		)

		# computation stage 2

		# count levels
		self.level = Signal(min=0, max=(num_nodes_per_pe*addresslayout.num_pe))
		self.sync += If(barrier2 & clock_enable, self.level.eq(self.level + 1))

		self.update = Signal()

		### User Code ###

		self.submodules.applykernel = BFSApplyKernel(addresslayout)

		self.comb += self.applykernel.nodeid_in.eq(dest_node_id2),\
					 self.applykernel.message_in.eq(payload2),\
					 self.applykernel.state_in.raw_bits().eq(rd_port.dat_r),\
					 self.applykernel.valid_in.eq(valid2),\
					 self.applykernel.barrier_in.eq(barrier2)

		self.comb += self.update.eq(self.applykernel.state_update)

		# if yes write parent value
		self.comb += wr_port.adr.eq(addresslayout.local_adr(dest_node_id2)),\
					 wr_port.dat_w.eq(self.applykernel.state_out.raw_bits()),\
					 wr_port.we.eq(self.update)

		# TODO: reset/init

		# collision handling	
		self.comb += collision.eq((dest_node_id == dest_node_id2) & valid & valid2 & self.update)

		# output handling
		_layout = [
		( "barrier", 1, DIR_M_TO_S ),
		( "msg" , payload_layout, DIR_M_TO_S )
		]
		self.submodules.outfifo = SyncFIFO(width_or_layout=set_layout_parameters(_layout, nodeidsize=nodeidsize), depth=addresslayout.num_nodes_per_pe)

		# stall if fifo full
		self.comb += clock_enable.eq(self.outfifo.writable & ~collision)
		# if parent is 0, we're resetting the table and don't want to send out messages.
		# if dest is 0, something went wrong before this point, but let's not make it worse.
		self.comb += self.outfifo.we.eq(self.applykernel.message_valid | self.applykernel.barrier_out),\
					 self.outfifo.din.msg.eq(self.applykernel.message_out),\
					 self.outfifo.din.barrier.eq(self.applykernel.barrier_out)

		self.comb += self.scatter_interface.msg.eq(self.outfifo.dout.msg),\
					 self.scatter_interface.barrier.eq(self.outfifo.dout.barrier),\
					 self.scatter_interface.valid.eq(self.outfifo.readable)

		# we can't send message (advance if receiver ready, or no data available) or if external request (has priority)
		self.comb += self.outfifo.re.eq(self.scatter_interface.ack & ~self.extern_rd_port.re)

if __name__ == "__main__":
	from migen.fhdl import verilog

	nodeidsize = 16
	num_nodes_per_pe = 2**8
	edgeidsize = 16
	max_edges_per_pe = 2**12
	peidsize = 8
	num_pe = 8

	addresslayout = BFSAddressLayout(nodeidsize, edgeidsize, peidsize, num_pe, num_nodes_per_pe, max_edges_per_pe)

	m = BFSApply(addresslayout)

	print(verilog.convert(m))
