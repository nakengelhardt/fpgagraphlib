import unittest

from migen import *
from tbsupport import *

from recordfifo import RecordFIFO
from core_interfaces import _msg_layout
from core_arbiter import Arbiter

from pr.config import config


class ArbiterCase(SimCase, unittest.TestCase):
    class TestBench(Module):
        def __init__(self):

            self.addresslayout = config(quiet=True)

            num_pe = self.addresslayout.num_pe

            msg_format = set_layout_parameters(_msg_layout, **self.addresslayout.get_params())
            
            self.fifos = [RecordFIFO(layout=msg_format, depth=32) for _ in range(num_pe)]
            self.submodules += self.fifos

            self.submodules.dut = Arbiter(self.addresslayout, self.fifos)

            self.messages_send = [(1, 171753), (2, 84960), (3, 80667), (4, 78659), (5, 34255), (6, 93813), (7, 132367)]
            self.messages = self.messages_send.copy()
    
    def test_arbiter(self):
        def gen_input():
            # send inputs
            for i in range(len(self.tb.fifos)):
                    yield self.tb.fifos[i].we.eq(0)
                    yield self.tb.fifos[i].din.barrier.eq(0)
            while self.tb.messages_send:
                dest_id, parent = self.tb.messages_send.pop()
                pe = dest_id % len(self.tb.fifos)
                # print("Sending message " + str((dest_id, parent)) + " on fifo " + str(pe))
                yield self.tb.fifos[pe].din.dest_id.eq(dest_id)
                yield self.tb.fifos[pe].din.payload.eq(parent)
                yield self.tb.fifos[pe].we.eq(1)
                yield
                while not (yield self.tb.fifos[pe].writable):
                    yield
                yield self.tb.fifos[pe].we.eq(0)
                # print("Messages left: " + str(len(self.tb.messages_send)))
            yield
            for i in range(len(self.tb.fifos)):
                    yield self.tb.fifos[i].we.eq(1)
                    yield self.tb.fifos[i].din.barrier.eq(1)
            yield
            for i in range(len(self.tb.fifos)):
                    yield self.tb.fifos[i].we.eq(0)
                    yield self.tb.fifos[i].din.barrier.eq(0)

        def gen_output():
            # check output
            # TODO: add testing of pipeline stall by sometimes turning ack off?
            yield self.tb.dut.apply_interface.ack.eq(1)
            yield self.tb.dut.start_message.select.eq(0)
            
            msgs_received = 0
            total_msgs = len(self.tb.messages)
            # print("Total messages: " + str(total_msgs))
            while msgs_received < total_msgs:
                if (yield self.tb.dut.apply_interface.valid):
                    self.assertFalse((yield self.tb.dut.apply_interface.msg.barrier))
                    msg = ((yield self.tb.dut.apply_interface.msg.dest_id), (yield self.tb.dut.apply_interface.msg.payload))
                    # print("{0:{1}d}: {2}".format(msgs_received, len(str(total_msgs-1)), msg))
                    try:
                        self.tb.messages.remove(msg)
                        msgs_received += 1
                    except ValueError as e:
                        self.fail(msg="Unexpected message received: " + str(msg))
                yield
            if self.tb.messages:
                self.fail(msg="Messages not received: " + str(self.tb.messages))
            for i in range(20):
                if (yield self.tb.dut.apply_interface.valid) & (yield self.tb.dut.apply_interface.msg.barrier):
                    break
                yield
            else:
                self.fail("Barrier not reached")

        self.run_with([gen_input(), gen_output()], vcd_name="tb.vcd")

if __name__ == "__main__":
    unittest.main()