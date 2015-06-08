from migen.fhdl.std import *
from migen.genlib.fifo import SyncFIFO

from bfs_interfaces import BFSApplyInterface, BFSMessage
from migen.genlib.roundrobin import *


class BFSArbiter(Module):
	def __init__(self, num_pe, nodeidsize, fifos):
		self.apply_interface = BFSApplyInterface(nodeidsize)
		self.start_message = BFSApplyInterface(nodeidsize)

		self.submodules.roundrobin = RoundRobin(num_pe, switch_policy=SP_CE)

		array_dest_id = Array(fifo.dout.dest_id for fifo in fifos)
		array_parent = Array(fifo.dout.parent for fifo in fifos)
		array_re = Array(fifo.re for fifo in fifos)
		array_readable = Array(fifo.readable for fifo in fifos)

		self.comb += If(self.start_message.valid,
						self.apply_interface.msg.dest_id.eq(self.start_message.msg.dest_id),
						self.apply_interface.msg.parent.eq(self.start_message.msg.parent),
						self.apply_interface.valid.eq(self.start_message.valid),
						self.start_message.ack.eq(self.apply_interface.ack),
						self.roundrobin.ce.eq(0)
					 ).Else(
						self.apply_interface.msg.dest_id.eq(array_dest_id[self.roundrobin.grant]), 
						self.apply_interface.msg.parent.eq(array_parent[self.roundrobin.grant]), 
						self.apply_interface.valid.eq(array_readable[self.roundrobin.grant]),
						array_re[self.roundrobin.grant].eq(self.apply_interface.ack), 
						[self.roundrobin.request[i].eq(array_readable[i]) for i in range(len(fifos))], 
						self.roundrobin.ce.eq(self.apply_interface.ack)
					 )

if __name__ == '__main__':
	from migen.fhdl import verilog

	nodeidsize = 16
	num_pe = 2

	m = BFSArbiter(num_pe, nodeidsize, [SyncFIFO(width_or_layout=BFSMessage(nodeidsize).layout, depth=32) for _ in range(num_pe)])
	print(verilog.convert(m))