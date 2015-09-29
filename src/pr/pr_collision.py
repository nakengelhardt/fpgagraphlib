from migen.fhdl.std import *
from migen.fhdl.specials import READ_FIRST
from migen.genlib.record import *
from forwardmemory import ForwardMemory


class PRCollisionDetector(Module):
	def __init__(self, addresslayout):
		nodeidsize = addresslayout.nodeidsize
		num_nodes_per_pe = addresslayout.num_nodes_per_pe

		self.read_adr = Signal(nodeidsize)
		self.read_adr_valid = Signal()

		self.write_adr = Signal(nodeidsize)
		self.write_adr_valid = Signal()

		self.re = Signal()

		###

		# it takes one cycle to look up whether an address is in use or not.
		# therefore when address is invalid, raise stall signal, keeping data in next pipeline stage
		# need to save prev. address to know when it is released

		self.specials.mem = ForwardMemory(1, num_nodes_per_pe, init=[0 for _ in range(num_nodes_per_pe)])
		rw_port = self.mem.rw_port
		wr_port = self.mem.wr_port

		collision = Signal()

		# cannot at the same time write on both ports: in case of collision, deactivate wr_port
		# then determine manually if we need to stall by comparing with prev_adr
		self.comb += collision.eq((self.read_adr==self.write_adr) & self.read_adr_valid & self.write_adr_valid)
		
		# mark read state as invalid, unless it is currently being written
		self.comb += [
			rw_port.adr.eq(self.read_adr), 
			rw_port.dat_w.eq(1), 
			rw_port.we.eq(self.read_adr_valid & self.re),
			rw_port.re.eq(self.re)
		]

		# mark written state as valid
		self.comb += [
			wr_port.adr.eq(self.write_adr), 
			wr_port.dat_w.eq(0), 
			wr_port.we.eq(self.write_adr_valid & ~collision)
		]

		prev_adr = Signal(nodeidsize)
		prev_adr_valid = Signal()
		forward_flag = Signal()

		self.sync += [
			If(self.re, 
				prev_adr.eq(self.read_adr),
				prev_adr_valid.eq(self.read_adr_valid)
			),
			# in case of collision, we can move on by not writing back the flag, but just forwarding it immediately to re
			# unless collision happens while pipeline is stalled on a different address
			forward_flag.eq(collision & ~(~self.re & (self.write_adr!=prev_adr) & self.write_adr_valid & prev_adr_valid))
		]
		
		self.comb += [
			self.re.eq(~rw_port.dat_r | forward_flag)
		]