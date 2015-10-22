import unittest
import random

from migen import *
from tbsupport import *

from faddsub import FAddSub

class FAddSubCase(SimCase, unittest.TestCase):
    class TestBench(Module):
        def __init__(self):
            self.submodules.dut = FAddSub()

    def test_addsub(self):
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
        (7.504355E-39, 0.75859374), # a_expn < b_expn, a_expn == 0
        (0.0074023437, 7.504355E-39), # a_expn > b_expn, b_expn == 0
        (7.504355E-39, 6.034988E-39), # a_expn == b_expn == 0, a_mant > b_mant
        (7.504355E-39, 1.0443091E-38), # a_expn == b_expn == 0, a_mant > b_mant
        ]

        expected_num_answers = 2*len(testcases)
        self.answers = []
        self.done = False

        def gen_input():
            yield self.tb.dut.ce.eq(1)
            for a, b in testcases:
                yield self.tb.dut.a.eq(convert_float_to_32b_int(a))
                yield self.tb.dut.b.eq(convert_float_to_32b_int(b))
                yield self.tb.dut.valid_i.eq(1)
                yield self.tb.dut.sub.eq(0)
                yield
                while not random.choice([0,1]):
                    yield self.tb.dut.ce.eq(0)
                    yield
                yield self.tb.dut.ce.eq(1)
                yield self.tb.dut.sub.eq(1)
                yield
                while not random.choice([0,1]):
                    yield self.tb.dut.ce.eq(0)
                    yield
                yield self.tb.dut.ce.eq(1)
            yield self.tb.dut.valid_i.eq(0)
            yield
            while not self.done:
                yield self.tb.dut.ce.eq(random.choice([0,1]))
                yield
            yield self.tb.dut.ce.eq(1)

        def gen_output():
            while len(self.answers) < expected_num_answers:
                if (yield self.tb.dut.valid_o) & (yield self.tb.dut.ce):
                    self.answers.append(convert_32b_int_to_float((yield self.tb.dut.r)))
                yield
            self.done = True

        self.run_with([gen_input(), gen_output()])

        for i in range(len(testcases)):
            a, b = testcases[i]
            r1 = self.answers[2*i]
            r2 = self.answers[2*i+1]
            delta = 1E-6
            with self.subTest(a=a, b=b):
                self.assertAlmostEqual(r1, a+b, delta=delta)
                self.assertAlmostEqual(r2, a-b, delta=delta)

if __name__ == "__main__":
    unittest.main()