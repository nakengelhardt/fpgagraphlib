import unittest
import random

from migen import *
from tbsupport import *

from compactfifo import *

class CompactFifoCase(SimCase, unittest.TestCase):
    class TestBench(Module):
        def __init__(self):
            self.num_in = 9
            self.num_out = 3
            self.elementwidth = 32
            self.submodules.dut = SortEntryFIFO(elementwidth=self.elementwidth, num_in=self.num_in, num_out=self.num_out, depth=8)


    def test_conversion(self):
        inputs = []
        expected = []
        num_test_inputs = 100
        i = 0
        while i < num_test_inputs:
            data = 0
            valid = 0
            e = []
            for j in range(self.tb.num_in):
                data <<= self.tb.elementwidth
                valid <<= 1
                if random.choice([True, False]):
                    data |= i
                    valid |= 1
                    e.append(i)
                    i += 1
            inputs.append((valid, data))
            expected.extend(e[::-1])

        def gen_input():
            for valid, data in inputs:
                yield self.tb.dut.din.eq(data)
                yield self.tb.dut.we.eq(valid)
                yield
                while not (yield self.tb.dut.writable):
                    yield

        def gen_output():
            j = 0
            while j < num_test_inputs:
                yield self.tb.dut.re.eq(1) #random.choice([0,1]))
                if (yield self.tb.dut.readable) and (yield self.tb.dut.re):
                    dout = (yield self.tb.dut.dout)
                    nout = (yield self.tb.dut.readable)
                    for _ in range(nout):
                        self.assertEqual(dout & (2**self.tb.elementwidth - 1), expected[j])
                        dout >>= self.tb.elementwidth
                        j += 1
                yield

        @passive
        def gen_timeout(cycles):
            time = 0
            while time < cycles:
                yield
                time += 1
            self.fail("Timeout")

        self.run_with([gen_input(), gen_output(), gen_timeout(1000)], vcd_name="test_compactfifo.vcd")

if __name__ == "__main__":
    s = 42
    random.seed(s)
    unittest.main()
