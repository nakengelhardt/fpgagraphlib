from migen.fhdl.std import *
from migen.sim.generic import *

from fmul import FMul

import random
import struct

def _float_to_32b_int(f):
	return struct.unpack("I", struct.pack("f", f))[0]

def _32b_int_to_float(i):
	return struct.unpack("f", struct.pack("I", i))[0]

class AnswerGetter(Module):
	def __init__(self, dut):
		self.dut = dut
		self.answers = []
		self.expected_num_answers = float('inf')
		self.done = 0
	
	def gen_simulation(self, selfp):
		while len(self.answers) < self.expected_num_answers:
			if selfp.dut.valid_o & selfp.dut.ce:
				self.answers.append(_32b_int_to_float(selfp.dut.r))
			yield
		self.done = 1

class TB(Module):
	def __init__(self):
		self.submodules.dut = FMul()
		self.submodules.ans = AnswerGetter(self.dut)

	def gen_simulation(self, selfp):
		# helpful: http://www.h-schmidt.net/FloatConverter/IEEE754.html
		testcases = [ 
		# nonzero exponents
		(0.85, 0.0002), # a_expn > b_expn, a_mant > b_mant
		(-0.85, 0.054101564), # a_expn > b_expn, a_mant < b_mant
		(0.825, 12.075), # b_expn > a_expn, a_mant > b_mant
		(0.825, -15.2), # b_expn > a_expn, a_mant < b_mant
		(0.825, 0.7625), # a_expn == b_expn, a_mant > b_mant
		(-0.7625, -0.825), # a_expn == b_expn, a_mant < b_mant
		# zero exponents
		(1.525, 0.75859374), # a_expn > b_expn, a_expn == 0
		(0.0074023437, 1.77), # a_expn < b_expn, b_expn == 0
		(1.895, 1.395), # a_expn == b_expn == 0, a_mant > b_mant
		(1.895, 1.9575), # a_expn == b_expn == 0, a_mant > b_mant
		]

		self.ans.expected_num_answers = len(testcases)
		selfp.dut.ce = 1
		
		for a, b in testcases:
			selfp.dut.a = _float_to_32b_int(a)
			selfp.dut.b = _float_to_32b_int(b)
			selfp.dut.valid_i = 1
			yield
			while not random.choice([0,1]):
				selfp.dut.ce = 0
				yield
			selfp.dut.ce = 1
		selfp.dut.valid_i = 0
		yield
		while not self.ans.done:
			selfp.dut.ce = random.choice([0,1])
			yield
		selfp.dut.ce = 1
		yield

		err = False
		for i in range(len(testcases)):
			a, b = testcases[i]
			r = self.ans.answers[i]
			epsilon = 1E-6
			if abs(r - (a*b)) > epsilon:
				err = True
				print("Error: a*b = {}, r = {}".format(a*b, r))

		if not err:
			print("Test passed successfully.")



if __name__ == "__main__":
	tb = TB()
	run_simulation(tb, vcd_name="tb.vcd", ncycles=200)