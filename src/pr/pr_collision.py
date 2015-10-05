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

		self.submodules.mem = ForwardMemory(1, num_nodes_per_pe, init=[0 for _ in range(num_nodes_per_pe)])
		rw_port = self.mem.rw_port
		wr_port = self.mem.wr_port
		
		# mark read state as invalid
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
			wr_port.we.eq(self.write_adr_valid)
		]

		prev_adr = Signal(nodeidsize)
		prev_adr_valid = Signal()

		self.sync += [
			If(self.re, 
				prev_adr.eq(self.read_adr),
				prev_adr_valid.eq(self.read_adr_valid)
			)
		]
		
		self.comb += [
			self.re.eq(~rw_port.dat_r | ~prev_adr_valid)
		]