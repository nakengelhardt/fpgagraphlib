from migen.fhdl.std import *

from migen.genlib.fifo import SyncFIFO
from migen.genlib.roundrobin import *
from migen.genlib.misc import optree

from bfs_interfaces import BFSApplyInterface, BFSMessage



class BFSArbiter(Module):
	def __init__(self, addresslayout, fifos):
		nodeidsize = addresslayout.nodeidsize
		num_pe = addresslayout.num_pe

		# output
		self.apply_interface = BFSApplyInterface(nodeidsize=nodeidsize)

		# input override for injecting the message starting the computation
		self.start_message = BFSApplyInterface(nodeidsize=nodeidsize)

		self.submodules.roundrobin = RoundRobin(num_pe, switch_policy=SP_CE)

		# arrays for choosing incoming fifo to use
		array_data = Array(fifo.dout for fifo in fifos)
		array_re = Array(fifo.re for fifo in fifos)
		array_readable = Array(fifo.readable for fifo in fifos)
		array_barrier = Array(fifo.dout.barrier for fifo in fifos)

		barrier_reached = Signal()
		self.comb += barrier_reached.eq(optree("&", array_barrier))

		self.comb += If( self.start_message.valid, # override
						self.apply_interface.msg.eq(self.start_message.msg),
						self.apply_interface.valid.eq(self.start_message.valid),
						self.start_message.ack.eq(self.apply_interface.ack),
						self.roundrobin.ce.eq(0)
					 ).Elif( barrier_reached,
					 	self.apply_interface.msg.barrier.eq(1),
					 	self.apply_interface.valid.eq(1),
					 	[array_re[i].eq(self.apply_interface.ack) for i in range(len(fifos))]
					 ).Else( # normal roundrobin
						self.apply_interface.msg.eq(array_data[self.roundrobin.grant]),
						self.apply_interface.valid.eq(array_readable[self.roundrobin.grant] & ~ array_barrier[self.roundrobin.grant]),
						array_re[self.roundrobin.grant].eq(self.apply_interface.ack & ~ array_barrier[self.roundrobin.grant]), 
						[self.roundrobin.request[i].eq(array_readable[i] & ~ array_barrier[i]) for i in range(len(fifos))], 
						self.roundrobin.ce.eq(self.apply_interface.ack)
					 )
