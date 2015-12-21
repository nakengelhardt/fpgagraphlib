import unittest
import random

from migen import *
from migen.genlib.record import *
from recordfifo import RecordFIFO

from tbsupport import *

class FifoCase(SimCase, unittest.TestCase):
    class TestBench(Module):
        def __init__(self):
            self.layout = [
                ('a', 3, DIR_M_TO_S),
                ('b', 5, DIR_M_TO_S)
            ]
            self.init = [(1,2), (3,4), (5,6)]
            self.submodules.dut = RecordFIFO(layout=self.layout, depth=8, init=[convert_record_tuple_to_int(x, self.layout) for x in self.init], delay=3)

    def test_fifo(self):
        self.send = [(7,8), (2,10)]
        def gen_input():
            for a,b in self.send:
                yield self.tb.dut.din.a.eq(a)
                yield self.tb.dut.din.b.eq(b)
                yield self.tb.dut.we.eq(1)
                yield
                while not (yield self.tb.dut.writable):
                    yield
            yield self.tb.dut.we.eq(0)

        def gen_output():
            recvd = []
            yield self.tb.dut.re.eq(1)
            yield
            for _ in range(10):
                if (yield self.tb.dut.readable):
                    recvd.append(((yield self.tb.dut.dout.a), (yield self.tb.dut.dout.b)))
                yield
            self.assertListEqual(self.tb.init + self.send, recvd)

        self.run_with([gen_input(), gen_output()], vcd_name="test_fifo.vcd")


if __name__ == "__main__":
    unittest.main()