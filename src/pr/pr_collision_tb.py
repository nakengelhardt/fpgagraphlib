from migen.fhdl.std import *
from migen.sim.generic import *

from pr_collision import PRCollisionDetector
from pr_config import config



class TB(Module):
	def __init__(self, read_adr, write_adr, prev_adr, stall, expected):
		addresslayout = config(quiet=True)
		self.submodules.dut = PRCollisionDetector(addresslayout)
		self.read_adr = read_adr
		self.write_adr = write_adr
		self.prev_adr = prev_adr
		self.stall = stall
		self.expected = expected

		init = [0 for _ in range(self.dut.mem.mem.depth)]
		init[prev_adr] = int(stall)
		self.dut.mem.mem.init = init

		self.passed = 1

	def gargle(self, b):
		if b:
			print("...passed.")
		else:
			self.passed = 0
			print("...failed!")

	def gen_simulation(self, selfp):

		# currently invalid: 3
		# set prev_adr
		selfp.dut.read_adr = self.prev_adr
		selfp.dut.read_adr_valid = 1

		selfp.dut.write_adr = 0
		selfp.dut.write_adr_valid = 0

		yield

		# init before, cannot have stalled yet
		self.gargle(selfp.dut.re == 1)

		# make 3 valid again
		selfp.dut.read_adr = self.read_adr
		selfp.dut.read_adr_valid = 1

		selfp.dut.write_adr = self.write_adr
		selfp.dut.write_adr_valid = 1

		yield

		# prev_adr is 2, not invalid
		self.gargle(selfp.dut.re == self.expected)




if __name__ == "__main__":
	inputs = [
		[1, 2, 3, 0, 1],
		[1, 2, 3, 1, 0],
		[1, 2, 1, 0, 1],
		[1, 2, 1, 1, 0],
		[1, 1, 3, 0, 1],
		[1, 1, 3, 1, 0],
		[1, 2, 2, 0, 1],
		[1, 2, 2, 1, 0],
		[1, 1, 1, 0, 1],
		[1, 1, 1, 1, 0]
	]
	for testcase, l in enumerate(inputs):
		print("Testcase {}".format(testcase))
		tb = TB(read_adr=l[0], write_adr=l[1], prev_adr=l[2], stall=l[3], expected=l[4])
		run_simulation(tb, vcd_name=None, ncycles=200)
		if not tb.passed:
			tb = TB(read_adr=l[0], write_adr=l[1], prev_adr=l[2], stall=l[3], expected=l[4])
			run_simulation(tb, vcd_name="pr_collision_tb_{}_failed.vcd".format(testcase), ncycles=200)