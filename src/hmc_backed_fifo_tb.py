from migen import *
from tbsupport import *
from migen.fhdl import verilog

from util.recordfifo import *

from util.pico import *

from hmc_backed_fifo import HMCBackedFIFO

import unittest
import random


class HMCBackedFIFOCase(SimCase, unittest.TestCase):
    class TestBench(Module):
        def __init__(self):
            self.data = [x for x in range(32)]

            pico = PicoPlatform(1, bus_width=32, stream_width=128)

            num_dut = 2
            self.submodules.dut = [HMCBackedFIFO(width=32, start_addr=i*0x10000, end_addr=(i+1)*0x10000, port=pico.getHMCPort(i)) for i in range(num_dut)]

    def test_rw(self):
        def gen_write(i):
            for x in self.tb.data:
                yield self.tb.dut[i].din.eq(x+i*32)
                yield self.tb.dut[i].we.eq(1)
                yield
                while not (yield self.tb.dut[i].writable):
                    yield
            yield self.tb.dut[i].we.eq(0)

        def gen_read(i):
            yield self.tb.dut[i].re.eq(1)
            for x in self.tb.data:
                yield
                while not (yield self.tb.dut[i].readable):
                    yield
                self.assertEqual(x+i*32, (yield self.tb.dut[i].dout))
                print(i, x+i*32)
            for _ in range(3):
                yield
                self.assertEqual(0, (yield self.tb.dut[i].readable))
            yield self.tb.dut[i].re.eq(0)

        @passive
        def gen_timeout(cycles):
            time = 0
            while time < cycles:
                yield
                time += 1
            self.fail("Timeout")

        generators = [gen_timeout(1000)]
        for i, dut in enumerate(self.tb.dut):
            generators.extend([dut.port.gen_responses(), gen_write(i), gen_read(i)])
        self.run_with(generators, vcd_name="test_hmc_rw.vcd")



if __name__ == "__main__":
    s = 42
    random.seed(s)
    unittest.main()
