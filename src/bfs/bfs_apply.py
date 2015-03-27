from migen.fhdl.std import *
# from migen.genlib.fsm import FSM, NextState, NextValue
# from migen.fhdl import verilog

# assumes 0 is not a valid nodeID
class BFSApply(Module):
	def __init__(self, nodeidsize, num_nodes_per_pe):
		# input Q interface
		# indicate ready, receive one message with valid
		# message format (dest_node_id, parent)
		self.recv_ready = Signal()
		self.recv_msg = Signal(2 * nodeidsize)
		self.recv_msg_valid = Signal()

		# scatter interface
		# send update message to all neighbors
		# message format (sending_node_id) (normally would be (sending_node_id, payload), but for BFS payload = sending_node_id)
		self.scatter_ready = Signal()
		self.scatter_msg = Signal(nodeidsize)
		self.scatter_msg_valid = Signal()

		####

		# should pipeline advance?
		clock_enable = Signal()

		self.specials.mem = Memory(nodeidsize, num_nodes_per_pe, init=[0 for i in range(num_nodes_per_pe)])
		self.specials.rd_port = rd_port = self.mem.get_port()
		self.specials.wr_port = wr_port = self.mem.get_port(write_capable=True)

		# input handling
		self.comb += self.recv_ready.eq(clock_enable)

		# divide up msg (could be registered if necessary)
		dest_node_id1 = Signal(nodeidsize)
		parent1 = Signal(nodeidsize)
		valid1 = Signal()

		self.comb += dest_node_id1.eq(self.recv_msg[0:nodeidsize]), parent1.eq(self.recv_msg[nodeidsize:2*nodeidsize]), valid1.eq(self.recv_msg_valid)

		# computation stage 1

		# look up parent(dest_node_id) to see if already visited
		self.comb += rd_port.adr.eq(dest_node_id1)

		# registers to next stage
		dest_node_id2 = Signal(nodeidsize)
		parent2 = Signal(nodeidsize)
		valid2 = Signal()

		self.sync += If(clock_enable, 
			dest_node_id2.eq(dest_node_id1), 
			parent2.eq(parent1), 
			valid2.eq(valid1)
		)

		# computation stage 2

		# find out if we have an update
		update = Signal()
		self.comb += update.eq(valid2 & (rd_port.dat_r == 0))

		# if yes write parent value
		self.comb += wr_port.adr.eq(dest_node_id2), wr_port.dat_w.eq(parent2), wr_port.we.eq(update)
		# TODO: if next msg + one after is for same node, will not see updated value

		# output handling
		# if update (= node hadn't been previously visited), scatter own id (= visit children)
		
		self.comb += self.scatter_msg.eq(dest_node_id2), self.scatter_msg_valid.eq(update)

		# stall if we can't send message
		self.comb += clock_enable.eq(self.scatter_ready)