import unittest
import random

from migen import *
from migen.genlib.record import *

from tbsupport import *
from bfs.config import Config
from graph_generate import generate_graph

from ring_network import Network

class NetworkCase(SimCase, unittest.TestCase):
    class TestBench(Module):
        def __init__(self):
            pe_id = 0

            self.graph = generate_graph(num_nodes=31, num_edges=60)
            # print(self.graph)

            self.config = Config(self.graph, nodeidsize=32, edgeidsize=32, peidsize=2, num_pe=4, num_nodes_per_pe=8, max_edges_per_pe=64, pe_groups=1, inter_pe_delay=0, use_hmc=False, share_mem_port=False, num_channels=4, channel_bits=2)
            self.submodules.dut = Network(self.config)

    def test_network(self):
        sent = [[] for _ in range(self.tb.config.addresslayout.num_pe)]
        received = [[] for _ in range(self.tb.config.addresslayout.num_pe)]
        num_sent = [[0 for _ in range(self.tb.config.addresslayout.num_pe)] for _ in range(self.tb.config.addresslayout.num_pe)]
        for node in self.tb.graph:
            for neighbor in self.tb.graph[node]:
                sender_pe = self.tb.config.addresslayout.pe_adr(node)
                dest_pe = self.tb.config.addresslayout.pe_adr(neighbor)
                msg = {"dest_id": neighbor, "sender": node, "payload": 0, "barrier":0, "dest_pe": dest_pe}
                sent[sender_pe].append(msg)
                num_sent[sender_pe][dest_pe] += 1
                received[dest_pe].append(msg)

        # print("Messages to send:")
        # for pe in range(self.tb.config.addresslayout.num_pe):
        #     print("PE {}: {}".format(pe, sent[pe]))

        def gen_input(pe, num_rounds):
            for roundpar in range(num_rounds):
                messages = sent[pe].copy()
                [messages.append({"dest_id": num_sent[pe][i], "sender": pe << log2_int(self.tb.config.addresslayout.num_nodes_per_pe), "payload": 0, "barrier": 1, "dest_pe": i}) for i in range(self.tb.config.addresslayout.num_pe)]
                while messages:
                    msg = messages.pop(random.randrange(len(messages)))
                    yield (self.tb.dut.network_interface[pe].msg.dest_id.eq(msg["dest_id"]))
                    yield (self.tb.dut.network_interface[pe].msg.sender.eq(msg["sender"]))
                    yield (self.tb.dut.network_interface[pe].msg.payload.eq(msg["payload"]))
                    yield (self.tb.dut.network_interface[pe].msg.barrier.eq(msg["barrier"]))
                    yield (self.tb.dut.network_interface[pe].msg.roundpar.eq(roundpar))
                    yield (self.tb.dut.network_interface[pe].dest_pe.eq(msg["dest_pe"]))
                    yield (self.tb.dut.network_interface[pe].broadcast.eq(msg["barrier"]))
                    yield (self.tb.dut.network_interface[pe].valid.eq(random.choice([0,1])))
                    yield
                    while not ((yield self.tb.dut.network_interface[pe].valid) and (yield self.tb.dut.network_interface[pe].ack)):
                        yield (self.tb.dut.network_interface[pe].valid.eq(random.choice([0,1])))
                        yield
            yield (self.tb.dut.network_interface[pe].valid.eq(0))
            yield

        def gen_output(pe, num_rounds):
            for roundpar in range(num_rounds):
                messages = received[pe].copy()
                print("PE {} entering round {}. Messages expected: {}".format(pe, roundpar, messages))
                while messages:
                    yield (self.tb.dut.apply_interface[pe].ack.eq(random.choice([0,1])))
                    if (yield self.tb.dut.apply_interface[pe].valid) and (yield self.tb.dut.apply_interface[pe].ack):
                        dest_id = yield self.tb.dut.apply_interface[pe].msg.dest_id
                        sender = yield self.tb.dut.apply_interface[pe].msg.sender
                        payload = yield self.tb.dut.apply_interface[pe].msg.payload
                        barrier = yield self.tb.dut.apply_interface[pe].msg.barrier
                        rnd = yield self.tb.dut.apply_interface[pe].msg.roundpar
                        print("PE {} received message ({} -> {})".format(pe, sender, dest_id))
                        self.assertFalse(barrier)
                        self.assertEqual(rnd, roundpar)
                        for msg in messages:
                            if (msg["dest_id"] == dest_id) and (msg["sender"] == sender):
                                messages.remove(msg)
                                break
                        else:
                            self.fail("PE {} received message {}".format(pe, msg))
                    yield
                print("PE {} received all messages of round {}".format(pe, roundpar))

                while True:
                    yield (self.tb.dut.apply_interface[pe].ack.eq(random.choice([0,1])))
                    if (yield self.tb.dut.apply_interface[pe].valid) and (yield self.tb.dut.apply_interface[pe].ack):
                        dest_id = yield self.tb.dut.apply_interface[pe].msg.dest_id
                        sender = yield self.tb.dut.apply_interface[pe].msg.sender
                        payload = yield self.tb.dut.apply_interface[pe].msg.payload
                        barrier = yield self.tb.dut.apply_interface[pe].msg.barrier
                        rnd = yield self.tb.dut.apply_interface[pe].msg.roundpar
                        print("PE {} received barrier (round {})".format(pe, rnd))
                        self.assertTrue(barrier)
                        self.assertEqual(rnd, roundpar, "PE {} expected round {} but received round {}".format(pe, roundpar, rnd))
                        break
                    yield
                yield
            yield (self.tb.dut.apply_interface[pe].ack.eq(0))



        @passive
        def gen_timeout(cycles):
            time = 0
            while time < cycles:
                yield
                time += 1
            print("Not received: " + str([e for l in received for e in l]))
            self.fail("Timeout")

        num_rounds = 3
        self.run_with([gen_input(i,num_rounds) for i in range(self.tb.config.addresslayout.num_pe)] +[gen_output(i,num_rounds) for i in range(self.tb.config.addresslayout.num_pe)] + [gen_timeout(300*num_rounds)], vcd_name="test_network.vcd")

if __name__ == "__main__":
    unittest.main()
