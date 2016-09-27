import unittest
import random

from migen import *
from migen.genlib.record import *

from tbsupport import *
from bfs.config import Config
from graph_generate import generate_graph

from core_arbiter import Arbiter

class ArbiterCase(SimCase, unittest.TestCase):
    class TestBench(Module):
        def __init__(self):
            pe_id = 0

            self.graph = generate_graph(num_nodes=15, num_edges=30)
            # print(self.graph)

            self.config = Config(self.graph, nodeidsize=32, edgeidsize=32, peidsize=1, num_pe=2, num_nodes_per_pe=8, max_edges_per_pe=64, pe_groups=1, inter_pe_delay=0, use_hmc=False, share_mem_port=False, num_channels=4, channel_bits=2)
            self.submodules.dut = Arbiter(pe_id, self.config)

    def test_arbiter(self):
        sent = []
        num_sent = [0 for _ in range(self.tb.config.addresslayout.num_pe)]
        for node in self.tb.graph:
            for neighbor in self.tb.graph[node]:
                if self.tb.config.addresslayout.pe_adr(neighbor) == 0:
                    sent.append({"dest_id": neighbor, "sender": node, "payload": 0, "barrier":0, "roundpar": 0})
                    num_sent[self.tb.config.addresslayout.pe_adr(node)] += 1

        def gen_input(roundpar):
            messages = sent.copy()
            [messages.append({"dest_id": num_sent[i], "sender": i << log2_int(self.tb.config.addresslayout.num_nodes_per_pe), "payload": 0, "barrier": 1, "roundpar": 0}) for i in range(self.tb.config.addresslayout.num_pe)]
            while messages:
                msg = messages.pop(random.randrange(len(messages)))
                yield self.tb.dut.apply_interface_in[roundpar].msg.dest_id.eq(msg["dest_id"])
                yield self.tb.dut.apply_interface_in[roundpar].msg.sender.eq(msg["sender"])
                yield self.tb.dut.apply_interface_in[roundpar].msg.payload.eq(msg["payload"])
                yield self.tb.dut.apply_interface_in[roundpar].msg.barrier.eq(msg["barrier"])
                yield self.tb.dut.apply_interface_in[roundpar].msg.roundpar.eq(roundpar)
                yield self.tb.dut.apply_interface_in[roundpar].valid.eq(1)
                yield
                while not (yield self.tb.dut.apply_interface_in[roundpar].ack):
                    yield

        def gen_output(test_rounds):
            for i in range(test_rounds):
                to_receive = sent.copy()
                while to_receive:
                    yield self.tb.dut.apply_interface_out.ack.eq(random.choice([0,1]))
                    if (yield self.tb.dut.apply_interface_out.valid) and (yield self.tb.dut.apply_interface_out.ack):
                        dest_id = (yield self.tb.dut.apply_interface_out.msg.dest_id)
                        sender = (yield self.tb.dut.apply_interface_out.msg.sender)
                        payload = (yield self.tb.dut.apply_interface_out.msg.payload)
                        barrier = (yield self.tb.dut.apply_interface_out.msg.barrier)
                        roundpar = (yield self.tb.dut.apply_interface_out.msg.roundpar)

                        try:
                            self.assertFalse(barrier)
                            self.assertEqual(roundpar, i)
                        except AssertionError as e:
                            yield
                            raise e

                        for d in to_receive:
                            if d["sender"] == sender and d["dest_id"] == dest_id:
                                to_receive.remove(d)
                    yield
                while not ((yield self.tb.dut.apply_interface_out.valid) and (yield self.tb.dut.apply_interface_out.ack)):
                    yield self.tb.dut.apply_interface_out.ack.eq(random.choice([0,1]))
                    yield
                barrier = (yield self.tb.dut.apply_interface_out.msg.barrier)
                self.assertTrue(barrier)
                yield
            # TODO: add test that all messages are unchanged

        @passive
        def gen_timeout(cycles):
            time = 0
            while time < cycles:
                yield
                time += 1
            # print("Not received: " + str(to_receive))
            self.fail("Timeout")

        self.run_with([gen_input(0), gen_input(1), gen_input(2), gen_output(3), gen_timeout(10000)], vcd_name="test_arbiter.vcd")

if __name__ == "__main__":
    unittest.main()
