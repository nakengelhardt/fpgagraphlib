from migen.fhdl.std import *
from migen.genlib.record import *
from migen.genlib.fifo import SyncFIFO

from pr_interfaces import PRApplyInterface, PRScatterInterface, PRMessage, node_storage_layout
from pr_address import PRAddressLayout
from pr_config import config
from pr_collision import PRCollisionDetector
from pr_applykernel import PRApplyKernel
from forwardmemory import ForwardMemory


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
		upstream_ack = Signal()

		# local node data storage
		if init_nodedata == None:
			init_nodedata = [0 for i in range(num_nodes_per_pe)]
		self.submodules.mem = ForwardMemory(layout_len(set_layout_parameters(node_storage_layout, **addresslayout.get_params())), num_nodes_per_pe, init=init_nodedata)
		rd_port = self.mem.rw_port
		wr_port = self.mem.wr_port

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
		self.comb += self.apply_interface.ack.eq(upstream_ack)

		# detect termination (if all PEs receive 2 barriers in a row)
		self.inactive = Signal()
		prev_was_barrier = Signal()
		prev_prev_was_barrier = Signal()
		self.sync += If(self.apply_interface.valid & self.apply_interface.ack, prev_was_barrier.eq(self.apply_interface.msg.barrier))
		self.sync += If(self.apply_interface.valid & self.apply_interface.ack, prev_prev_was_barrier.eq(prev_was_barrier))
		self.comb += self.inactive.eq(prev_was_barrier & prev_prev_was_barrier)

		## Stage 1
		# rename some signals for easier reading, separate barrier and normal valid (for writing to state mem)
		dest_node_id = Signal(nodeidsize)
		payload = Signal(addresslayout.payloadsize)
		valid = Signal()
		barrier = Signal()

		self.comb += dest_node_id.eq(self.apply_interface.msg.dest_id),\
					 payload.eq(self.apply_interface.msg.payload),\
					 valid.eq(self.apply_interface.valid & ~self.apply_interface.msg.barrier),\
					 barrier.eq(self.apply_interface.valid & self.apply_interface.msg.barrier)

		# collision handling
		collision_re = Signal()
		self.submodules.collisiondetector = PRCollisionDetector(addresslayout)

		self.comb += self.collisiondetector.read_adr.eq(addresslayout.local_adr(dest_node_id)),\
					 self.collisiondetector.read_adr_valid.eq(valid),\
					 self.collisiondetector.write_adr.eq(wr_port.adr),\
					 self.collisiondetector.write_adr_valid.eq(wr_port.we),\
					 collision_re.eq(self.collisiondetector.re)


		# get node data
		self.comb += local_rd_port.adr.eq(addresslayout.local_adr(dest_node_id)),\
					 local_rd_port.re.eq(upstream_ack)


		## Stage 3
		dest_node_id2 = Signal(nodeidsize)
		payload2 = Signal(addresslayout.payloadsize)
		valid2 = Signal()
		barrier2 = Signal()
		data_invalid2 = Signal()
		ready = Signal()

		self.sync += If(upstream_ack, 
			dest_node_id2.eq(dest_node_id), 
			payload2.eq(payload), 
			valid2.eq(valid),
			barrier2.eq(barrier)
		)

		# count levels
		self.level = Signal(32)
		self.sync += If(barrier2 & ready, self.level.eq(self.level + 1))

		downstream_ack = Signal()

		# User code
		self.submodules.applykernel = PRApplyKernel(addresslayout)

		self.comb += self.applykernel.nodeid_in.eq(dest_node_id2),\
					 self.applykernel.message_in.raw_bits().eq(payload2),\
					 self.applykernel.state_in.raw_bits().eq(local_rd_port.dat_r),\
					 self.applykernel.valid_in.eq(valid2 & collision_re),\
					 self.applykernel.barrier_in.eq(barrier2),\
					 self.applykernel.level_in.eq(self.level),\
					 self.applykernel.message_ack.eq(downstream_ack),\
					 ready.eq(self.applykernel.ready),\
					 upstream_ack.eq(self.applykernel.ready & collision_re)


		# if yes write parent value
		self.comb += wr_port.adr.eq(addresslayout.local_adr(self.applykernel.nodeid_out)),\
					 wr_port.dat_w.eq(self.applykernel.state_out.raw_bits()),\
					 wr_port.we.eq(self.applykernel.state_valid)

		# TODO: reset/init

		
		# output handling
		_layout = [
		( "barrier", 1, DIR_M_TO_S ),
		( "sender", "nodeidsize", DIR_M_TO_S ),
		( "msg" , addresslayout.payloadsize, DIR_M_TO_S )
		]
		self.submodules.outfifo = SyncFIFO(width_or_layout=set_layout_parameters(_layout, **addresslayout.get_params()), depth=addresslayout.num_nodes_per_pe)

		# stall if fifo full or if collision
		self.comb += downstream_ack.eq(self.outfifo.writable)

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