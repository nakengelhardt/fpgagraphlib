from migen.fhdl.std import *
from migen.sim.generic import *

from forwardmemory import ForwardMemory

class TB(Module):
	def __init__(self):
		width = 8
		depth = 32
		self.submodules.dut = ForwardMemory(width, depth, init=[i for i in range(depth)])

		self.tb_rw_port_adr = Signal(log2_int(depth))
		self.tb_rw_port_dat_r = Signal(width)
		self.tb_rw_port_re = Signal()
		self.tb_rw_port_dat_w = Signal(width)
		self.tb_rw_port_we = Signal()

		self.tb_wr_port_adr = Signal(log2_int(depth))
		self.tb_wr_port_dat_r = Signal(width)
		self.tb_wr_port_dat_w = Signal(width)
		self.tb_wr_port_we = Signal()

		self.comb += [
			self.dut.rw_port.adr.eq(self.tb_rw_port_adr),
			self.tb_rw_port_dat_r.eq(self.dut.rw_port.dat_r),
			self.dut.rw_port.re.eq(self.tb_rw_port_re),
			self.dut.rw_port.dat_w.eq(self.tb_rw_port_dat_w),
			self.dut.rw_port.we.eq(self.tb_rw_port_we),
			self.dut.wr_port.adr.eq(self.tb_wr_port_adr),
			self.dut.wr_port.dat_w.eq(self.tb_wr_port_dat_w),
			self.dut.wr_port.we.eq(self.tb_wr_port_we),
			self.tb_wr_port_dat_r.eq(self.dut.wr_port.dat_r)
		]



	def gen_simulation(self, selfp):

		selfp.tb_rw_port_adr = 0
		selfp.tb_rw_port_re = 1
		selfp.tb_rw_port_dat_w = 0
		selfp.tb_rw_port_we = 0

		selfp.tb_wr_port_adr = 1
		selfp.tb_wr_port_dat_w = 101
		selfp.tb_wr_port_we = 1

		yield

		selfp.tb_rw_port_re = 0

		selfp.tb_wr_port_adr = 0
		selfp.tb_wr_port_dat_w = 100
		selfp.tb_wr_port_we = 1

		yield

		selfp.tb_rw_port_adr = 4
		selfp.tb_rw_port_dat_w = 104
		selfp.tb_rw_port_we = 1
		selfp.tb_wr_port_we = 0

		yield

		selfp.tb_rw_port_adr = 4
		selfp.tb_rw_port_re = 1
		selfp.tb_rw_port_dat_w = 0
		selfp.tb_rw_port_we = 0

		yield 2

		selfp.tb_rw_port_adr = 5
		selfp.tb_rw_port_re = 1
		selfp.tb_rw_port_dat_w = 0
		selfp.tb_rw_port_we = 0

		yield

		selfp.tb_wr_port_adr = 5
		selfp.tb_wr_port_dat_w = 105
		selfp.tb_wr_port_we = 1

		yield

		selfp.tb_rw_port_re = 0

		selfp.tb_rw_port_we = 1
		selfp.tb_rw_port_dat_w = 205

		selfp.tb_wr_port_we = 0


		yield

		selfp.tb_rw_port_we = 0

		yield 3




if __name__ == "__main__":
	tb = TB()
	run_simulation(tb, vcd_name="tb.vcd", ncycles=200)