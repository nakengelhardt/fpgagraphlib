import unittest
import random

from migen import *
from migen.genlib.record import *

from tbsupport import *
from pico import unpack

from core_neighbors_hmcx4 import _data_layout, BurstDownconverter

class FifoCase(SimCase, unittest.TestCase):
    class TestBench(Module):
        def __init__(self):
            update_layout = set_layout_parameters(_data_layout, payloadsize=32, nodeidsize=32, edgeidsize=32)
            self.submodules.dut = BurstDownconverter(update_layout)


    def test_conversion(self):
        inputs = [(0x1234, 3, 1, 0, 12, 2, 0xDEADBEEF012345678BADF00DFACEFEED),
                  (0xABCD, 14, 2, 1, 9, 4, 0x76543210AAAAAAAABBBBCCCCDEDEDEDE)]
        expected = []
        for message, sender, from_pe, rnd, num_neighbors, valid, burst in inputs:
            for neighbor in unpack(burst, valid):
                expected.append((message, sender, rnd, num_neighbors, neighbor))
        received = []

        def gen_input():
            for message, sender, from_pe, rnd, num_neighbors, valid, burst in inputs:
                yield self.tb.dut.update_in.message.eq(message)
                yield self.tb.dut.update_in.sender.eq(sender)
                yield self.tb.dut.update_in.from_pe.eq(from_pe)
                yield self.tb.dut.update_in.round.eq(rnd)
                yield self.tb.dut.update_in.num_neighbors.eq(num_neighbors)
                yield self.tb.dut.update_in.valid.eq(valid)
                yield self.tb.dut.burst_in.eq(burst)

                yield self.tb.dut.valid_in.eq(1)
                yield

                while not (yield self.tb.dut.ack_in):
                    yield

                yield self.tb.dut.valid_in.eq(0)
                for i in range(random.randrange(4)+20):
                    yield

        def gen_output():
            yield self.tb.dut.neighbor_ack.eq(1)
            yield
            while len(received) < len(expected):
                if (yield self.tb.dut.neighbor_valid) and (yield self.tb.dut.neighbor_ack):
                    message = (yield self.tb.dut.message_out)
                    sender = (yield self.tb.dut.sender_out)
                    rnd = (yield self.tb.dut.round_out)
                    num_neighbors = (yield self.tb.dut.num_neighbors_out)
                    neighbor = (yield self.tb.dut.neighbor)
                    received.append((message, sender, rnd, num_neighbors, neighbor))
                yield self.tb.dut.neighbor_ack.eq(random.choice([0,1]))
                yield
            self.assertListEqual(expected, received)

        @passive
        def gen_timeout():
            time = 0
            while time < 100000:
                yield
                time += 1
            self.fail("Timeout: only received {}".format(received))

        self.run_with([gen_input(), gen_output(), gen_timeout()], vcd_name="test_downconv.vcd")

if __name__ == "__main__":
    unittest.main()
