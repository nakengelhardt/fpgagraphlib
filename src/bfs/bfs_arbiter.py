from migen.fhdl.std import *
from migen.genlib.fifo import SyncFIFO

from bfs_interfaces import BFSApplyInterface, BFSMessage
from migen.genlib.roundrobin import *


class BFSArbiter(Module):
	def __init__(self, num_pe, nodeidsize, fifos):
		# output
		self.apply_interface = BFSApplyInterface(nodeidsize)

		# input override for injecting the message starting the computation
		self.start_message = BFSApplyInterface(nodeidsize)

		self.submodules.roundrobin = RoundRobin(num_pe, switch_policy=SP_CE)

		# arrays for choosing incoming fifo to use
		array_data = Array(fifo.dout for fifo in fifos)
		array_re = Array(fifo.re for fifo in fifos)
		array_readable = Array(fifo.readable for fifo in fifos)

		self.comb += If(self.start_message.valid, # override
						self.apply_interface.msg.eq(self.start_message.msg),
						self.apply_interface.valid.eq(self.start_message.valid),
						self.start_message.ack.eq(self.apply_interface.ack),
						self.roundrobin.ce.eq(0)
					 ).Else( # normal roundrobin
						self.apply_interface.msg.eq(array_data[self.roundrobin.grant]),
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