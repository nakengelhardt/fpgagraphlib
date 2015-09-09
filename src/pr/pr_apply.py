from migen.fhdl.std import *
from migen.genlib.record import *
from migen.genlib.fifo import SyncFIFO

from pr_interfaces import PRApplyInterface, PRScatterInterface, PRMessage, node_storage_layout, payload_layout
from pr_address import PRAddressLayout
from pr_config import config


class PRApplyKernel(Module):
	def __init__(self, addresslayout):
		nodeidsize = addresslayout.nodeidsize
		fixedptfloatsize = addresslayout.fixedptfloatsize
		fixedptdecimals = addresslayout.fixedptdecimals

		self.nodeid_in = Signal(nodeidsize)
		self.message_in = Record(set_layout_parameters(payload_layout, **addresslayout.get_params()))
		self.state_in = Record(set_layout_parameters(node_storage_layout, **addresslayout.get_params()))
		self.valid_in = Signal()
		self.barrier_in = Signal()

		self.state_out = Record(set_layout_parameters(node_storage_layout, **addresslayout.get_params()))
		self.state_update = Signal()
		self.message_out = Record(set_layout_parameters(payload_layout, **addresslayout.get_params()))
		self.message_sender = Signal(nodeidsize)
		self.message_valid = Signal()
		self.barrier_out = Signal()
		self.message_ack = Signal()

		self.level = Signal(32)

		###

		const_base = addresslayout.const_base # init to int(0.15 / num_nodes * (2**fixedptdecimals))
		n_sum = Signal(fixedptfloatsize)
		n_nrecvd = Signal(nodeidsize)
		n_nneighbors = Signal(nodeidsize)

		dyn_rank = Signal(fixedptfloatsize + fixedptdecimals)


		self.comb += n_sum.eq(self.state_in.sum + self.message_in.weight),\
					 n_nrecvd.eq(self.state_in.nrecvd + 1),\
					 n_nneighbors.eq(self.state_in.nneighbors),\
					 dyn_rank.eq(int(0.85*(2**fixedptdecimals))*n_sum)

		self.comb += self.state_out.nneighbors.eq(n_nneighbors),\
					 If(self.level < 1, # init round
					 	self.state_out.nrecvd.eq(0),
					 	self.state_out.sum.eq(0),
					 	self.message_out.weight.eq(const_base),
					 	self.message_valid.eq(self.valid_in)
				 	 ).Elif(n_nrecvd < n_nneighbors, # not received all weights yet
						self.state_out.nrecvd.eq(n_nrecvd),
					 	self.state_out.sum.eq(n_sum),
						self.message_out.weight.eq(const_base + dyn_rank[fixedptdecimals:]),
						self.message_valid.eq(0)
					 ).Else( # received all data
						self.state_out.nrecvd.eq(0),
						self.state_out.sum.eq(0),
						self.message_out.weight.eq(const_base + dyn_rank[fixedptdecimals:]),
						self.message_valid.eq(self.valid_in & (self.level < 30)) # stop sending after 30 rounds
					 ),\
					 self.state_update.eq(self.valid_in),\
					 self.message_sender.eq(self.nodeid_in),\
					 self.barrier_out.eq(self.barrier_in)



## for wrapping signals when multiplexing memory port
_memory_port_layout = [
	( "enable", 1 ),
	( "adr", "adrsize" ),
	( "re", 1 ),
	( "dat_r", "datasize" )
]

class PRApply(Module):
	def __init__(self, addresslayout, init_nodedata=None):
		nodeidsize = addresslayout.nodeidsize
		num_nodes_per_pe = addresslayout.num_nodes_per_pe

		# input Q interface
		self.apply_interface = PRApplyInterface(**addresslayout.get_params())

		# scatter interface
		# send self.update message to all neighbors
		# message format (sending_node_id) (normally would be (sending_node_id, weight), but for PR weight = sending_node_id)
		self.scatter_interface = PRScatterInterface(**addresslayout.get_params())

		####

		# should pipeline advance?
		clock_enable = Signal()

		# local node data storage
		if init_nodedata == None:
			init_nodedata = [0 for i in range(num_nodes_per_pe)]
		self.specials.mem = Memory(layout_len(set_layout_parameters(node_storage_layout, **addresslayout.get_params())), num_nodes_per_pe, init=init_nodedata)
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

		# rename some signals for easier reading, separate barrier and normal valid (for writing to state mem)
		dest_node_id = Signal(nodeidsize)
		payload = Signal(addresslayout.payloadsize)
		valid = Signal()
		barrier = Signal()

		self.comb += dest_node_id.eq(self.apply_interface.msg.dest_id),\
					 payload.eq(self.apply_interface.msg.payload),\
					 valid.eq(self.apply_interface.valid & ~self.apply_interface.msg.barrier),\
					 barrier.eq(self.apply_interface.valid & self.apply_interface.msg.barrier)


		# get node data
		self.comb += local_rd_port.adr.eq(addresslayout.local_adr(dest_node_id)),\
					 local_rd_port.re.eq(clock_enable)
		

		# registers to next stage
		dest_node_id2 = Signal(nodeidsize)
		payload2 = Signal(addresslayout.payloadsize)
		valid2 = Signal()
		barrier2 = Signal()

		self.sync += If(clock_enable, 
			dest_node_id2.eq(dest_node_id), 
			payload2.eq(payload), 
			valid2.eq(valid),
			barrier2.eq(barrier)
		).Elif(collision,
			valid2.eq(0)
		)

		# computation stage 2

		# count levels
		self.level = Signal(32)
		self.sync += If(barrier2 & clock_enable, self.level.eq(self.level + 1))

		self.update = Signal()

		####### User code ########

		self.submodules.applykernel = PRApplyKernel(addresslayout)

		self.comb += self.applykernel.nodeid_in.eq(dest_node_id2),\
					 self.applykernel.message_in.raw_bits().eq(payload2),\
					 self.applykernel.state_in.raw_bits().eq(rd_port.dat_r),\
					 self.applykernel.valid_in.eq(valid2),\
					 self.applykernel.barrier_in.eq(barrier2),\
					 self.applykernel.level.eq(self.level)

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
		( "sender", "nodeidsize", DIR_M_TO_S ),
		( "msg" , addresslayout.payloadsize, DIR_M_TO_S )
		]
		self.submodules.outfifo = SyncFIFO(width_or_layout=set_layout_parameters(_layout, **addresslayout.get_params()), depth=addresslayout.num_nodes_per_pe)

		# stall if fifo full or if collision
		self.comb += clock_enable.eq(self.outfifo.writable & ~collision)

		self.comb += self.outfifo.we.eq(self.applykernel.message_valid | self.applykernel.barrier_out),\
					 self.outfifo.din.msg.eq(self.applykernel.message_out.raw_bits()),\
					 self.outfifo.din.sender.eq(self.applykernel.message_sender),\
					 self.outfifo.din.barrier.eq(self.applykernel.barrier_out)

		self.comb += self.scatter_interface.msg.eq(self.outfifo.dout.msg),\
					 self.scatter_interface.sender.eq(self.outfifo.dout.sender),\
					 self.scatter_interface.barrier.eq(self.outfifo.dout.barrier),\
					 self.scatter_interface.valid.eq(self.outfifo.readable)

		# send from fifo when receiver ready and no external request (has priority)
		self.comb += self.outfifo.re.eq(self.scatter_interface.ack & ~self.extern_rd_port.re)

if __name__ == "__main__":
	from migen.fhdl import verilog

	addresslayout = config()

	m = PRApply(addresslayout)

	print(verilog.convert(m))

	print(addresslayout.get_params())