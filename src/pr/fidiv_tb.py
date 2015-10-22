import unittest
import random

from migen import *
from tbsupport import *

from fidiv import FloatIntDivider

class FIDivCase(SimCase, unittest.TestCase):
    class TestBench(Module):
        def __init__(self):
            self.submodules.dut = FloatIntDivider()

    def test_division(self):

        testcases = [(dividend, divisor) for dividend in [36.0, 0, -0.7625, 7.504355E-39] for divisor in range(1, 16)]
        answers = []
        self.done = False

        testce = [0, 1]

        def gen_input():
            yield self.tb.dut.ce.eq(1)
            for dividend, divisor in testcases:
                yield self.tb.dut.dividend_i.eq(convert_float_to_32b_int(float(dividend)))
                yield self.tb.dut.divisor_i.eq(divisor)
                yield self.tb.dut.valid_i.eq(1)
                yield
                while not random.choice(testce):
                    yield self.tb.dut.ce.eq(0)
                    yield
                yield self.tb.dut.ce.eq(1)
            yield self.tb.dut.valid_i.eq(0)
            yield
            while not self.done:
                yield self.tb.dut.ce.eq(random.choice(testce))
                yield
            yield self.tb.dut.ce.eq(1)

        def gen_output():
            while len(answers) < len(testcases):
                if (yield self.tb.dut.valid_o) & (yield self.tb.dut.ce):
                    answers.append(convert_32b_int_to_float((yield self.tb.dut.quotient_o)))
                yield
            self.done = True
                        
        self.run_with([gen_input(), gen_output()], vcd_name="tb.vcd")

        for i in range(len(testcases)):
            dividend, divisor = testcases[i]
            quotient = answers[i]
            with self.subTest(dividend=dividend, divisor=divisor):
                self.assertAlmostEqual(quotient, dividend/divisor, delta=1E-6)

if __name__ == "__main__":
    s = 42
    random.seed(s)
    print("Random seed: " + str(s))
    unittest.main()