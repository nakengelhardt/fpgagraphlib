from migen.fhdl.std import *
from migen.fhdl.specials import READ_FIRST
from types import SimpleNamespace

class ForwardMemory(Module):
	"""Memory with handling for concurrent reads and writes.
	rw_port is used to read status and set flag, wr_port is used to unset flag.
	If all three are used concurrently, order of operations is unset, read, set.

	rw_port.re changes address from which is read, but data is updated when	changed
	even if re is 0."""
	def __init__(self, width, depth, init=None):
		self.specials.mem = Memory(width, depth, init=init)
		self.specials.internal_rw_port = internal_rw_port = self.mem.get_port(write_capable=True, has_re=True, mode=READ_FIRST)
		self.specials.internal_wr_port = internal_wr_port = self.mem.get_port(write_capable=True, mode=READ_FIRST)

		self.rw_port = SimpleNamespace( adr=Signal(flen(internal_rw_port.adr), name="rw_port_adr"),
										dat_r=Signal(width, name="rw_port_dat_r"), 
										re=Signal(name="rw_port_re"), 
										dat_w=Signal(width, name="rw_port_dat_w"), 
										we=Signal(name="rw_port_we") )
		self.wr_port = SimpleNamespace( adr=Signal(flen(internal_wr_port.adr), name="wr_port_adr"), 
										dat_r=Signal(width, name="wr_port_dat_r"), 
										re=Signal(name="wr_port_re"), 
										dat_w=Signal(width, name="wr_port_dat_w"), 
										we=Signal(name="wr_port_we") )

		old_address = Signal(flen(internal_rw_port.adr))
		new_data_wr = Signal(width)
		new_data_rw = Signal(width)

		collision = Signal()
		forward_wr = Signal()
		forward_rw = Signal()

		self.sync += [
			If(self.rw_port.re, old_address.eq(self.rw_port.adr)),
			If(self.wr_port.we, new_data_wr.eq(self.wr_port.dat_w)),
			If(self.rw_port.we, new_data_rw.eq(self.rw_port.dat_w)),
			collision.eq(((self.wr_port.adr == self.rw_port.adr) & self.wr_port.we & self.rw_port.re)),
			If(self.rw_port.re,
				forward_wr.eq(0)
			).Elif((self.wr_port.adr == old_address) & self.wr_port.we,
				forward_wr.eq(1)
			),
			If((self.wr_port.adr == self.rw_port.adr) & self.wr_port.we & self.rw_port.we & self.rw_port.re,
				forward_rw.eq(1)
			).Elif(self.rw_port.re,
				forward_rw.eq(0)
			)
		]

		self.comb += [
			internal_rw_port.adr.eq(self.rw_port.adr),
			internal_rw_port.re.eq(self.rw_port.re),
			internal_rw_port.dat_w.eq(self.rw_port.dat_w),
			internal_rw_port.we.eq(self.rw_port.we),
			If(forward_wr | collision, 
				self.rw_port.dat_r.eq(new_data_wr)
			).Elif(forward_rw,
				self.rw_port.dat_r.eq(new_data_rw)
			).Else(
				self.rw_port.dat_r.eq(internal_rw_port.dat_r)
			),
			internal_wr_port.adr.eq(self.wr_port.adr),
			internal_wr_port.dat_w.eq(self.wr_port.dat_w),
			internal_wr_port.we.eq(self.wr_port.we & ~self.rw_port.we),
			self.wr_port.dat_r.eq(internal_wr_port.dat_r)
		]