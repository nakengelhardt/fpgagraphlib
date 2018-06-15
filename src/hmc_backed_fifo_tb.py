from migen import *
from tbsupport import *
from migen.fhdl import verilog

from recordfifo import *

from pico import *

from hmc_backed_fifo import HMCBackedFIFO

import unittest
import random


class HMCBackedFIFOCase(SimCase, unittest.TestCase):
    class TestBench(Module):
        def __init__(self):
            self.data = [x for x in range(32)]

            pico = PicoPlatform(1, bus_width=32, stream_width=128)

            self.submodules.dut = HMCBackedFIFO(width=32, start_addr=0x1000, end_addr=0x11000, port=pico.getHMCPort(0))

    def test_rw(self):
        def gen_write():
            for x in self.tb.data:
                yield self.tb.dut.din.eq(x)
                yield self.tb.dut.we.eq(1)
                yield
                while not (yield self.tb.dut.writable):
                    yield
            yield self.tb.dut.we.eq(0)

        def gen_read():
            yield self.tb.dut.re.eq(1)
            for x in self.tb.data:
                yield
                while not (yield self.tb.dut.readable):
                    yield
                self.assertEqual(x, (yield self.tb.dut.dout))
                print(x)
            for _ in range(3):
                yield
                self.assertEqual(0, (yield self.tb.dut.readable))
            yield self.tb.dut.re.eq(0)

        @passive
        def gen_timeout(cycles):
            time = 0
            while time < cycles:
                yield
                time += 1
            self.fail("Timeout")

        self.run_with([gen_write(), gen_read(), gen_timeout(1000), self.tb.dut.port.gen_responses([])], vcd_name="test_hmc_rw.vcd")



if __name__ == "__main__":
    s = 42
    random.seed(s)
    unittest.main()
