from migen.fhdl.std import *
from migen.sim.generic import run_simulation

from fidiv import FloatIntDivider

import struct

def _float_to_32b_int(f):
	return struct.unpack("i", struct.pack("f", f))[0]

def _32b_int_to_float(i):
	return struct.unpack("f", struct.pack("i", i))[0]


class TB(Module):
	def __init__(self):
		self.submodules.dut = FloatIntDivider()

	def gen_simulation(self, selfp):
		selfp.dut.ce = 1
		selfp.dut.dividend_i = _float_to_32b_int(36)
		selfp.dut.divisor_i = 3
		selfp.dut.valid_i = 1
		yield
		print("In: cycle " + str(selfp.simulator.cycle_counter))
		selfp.dut.dividend_i = 0
		selfp.dut.divisor_i = 0
		selfp.dut.valid_i = 0
		while not selfp.dut.valid_o:
			yield
		print("Out: cycle " + str(selfp.simulator.cycle_counter))
		yield 5


if __name__ == "__main__":
	tb = TB()
	run_simulation(tb, vcd_name="tb.vcd", ncycles=200)