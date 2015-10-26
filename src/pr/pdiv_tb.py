from migen.fhdl.std import *
from migen.sim.generic import run_simulation

from pdiv import Divider

class TB(Module):
	def __init__(self):
		self.w = 4
		self.submodules.dut = Divider(self.w)

	def gen_simulation(self, selfp):
		selfp.dut.dividend_i = 6
		selfp.dut.divisor_i = 4
		selfp.dut.valid_i = 1
		yield
		selfp.dut.dividend_i = 9
		selfp.dut.divisor_i = 3
		yield
		selfp.dut.dividend_i = 0
		selfp.dut.divisor_i = 0
		selfp.dut.valid_i = 0
		yield self.w
		if selfp.dut.valid_o:
			print("Quotient:  " + str(selfp.dut.quotient_o))
			print("Remainder: " + str(selfp.dut.remainder_o))
		yield
		if selfp.dut.valid_o:
			print("Quotient:  " + str(selfp.dut.quotient_o))
			print("Remainder: " + str(selfp.dut.remainder_o))
		yield

if __name__ == "__main__":
	tb = TB()
	run_simulation(tb, vcd_name="tb.vcd", ncycles=200)