import unittest
import random

from migen import *
from tbsupport import *
from pico import PicoPlatform

from core_neighbors_hmcx4 import Neighborsx4
from pr.config import Config
from graph_generate import generate_graph


class NeighborCase(SimCase, unittest.TestCase):
    class TestBench(Module):
        def __init__(self):

            self.graph = generate_graph(num_nodes=15, num_edges=30)
            print(self.graph)

            self.config = Config(self.graph, nodeidsize=32, edgeidsize=32, peidsize=1, num_pe=1, num_nodes_per_pe=16, max_edges_per_pe=64, pe_groups=1, inter_pe_delay=0, use_hmc=True)
            self.config.platform = PicoPlatform(bus_width=32, stream_width=128)

            self.adj_idx = self.config.adj_idx[0]
            self.submodules.dut = Neighborsx4(pe_id=0, config=self.config)



    def test_neighbor(self):
        def gen_input():
            for node in self.tb.graph:
                idx, num = self.tb.adj_idx[node]
                neighbors = []
                for valid in self.tb.dut.valid:
                    yield valid.eq(0)
                pe = node % 4
                yield self.tb.dut.start_idx[pe].eq(idx)
                yield self.tb.dut.num_neighbors[pe].eq(num)
                yield self.tb.dut.sender_in[pe].eq(node)
                yield self.tb.dut.message_in[pe].eq(node)
                yield self.tb.dut.valid[pe].eq(1)
                yield
                while not (yield self.tb.dut.ack[pe]):
                    yield
            for valid in self.tb.dut.valid:
                yield valid.eq(0)
            for barrier_in in self.tb.dut.barrier_in:
                yield barrier_in.eq(1)
            yield
            ack = [False for _ in range(4)]
            while not (ack[0] and ack[1] and ack[2] and ack[3]):
                for i in range(4):
                    if (yield self.tb.dut.ack[i]):
                        ack[i] = True
                        yield self.tb.dut.barrier_in[i].eq(0)
                yield
            yield

        neighbors = dict()
        def gen_output():
            for k in self.tb.graph:
                neighbors[k] = self.tb.graph[k].copy()
            while neighbors:
                for i in range(4):
                    yield self.tb.dut.neighbor_ack[i].eq(random.choice([0,1]))
                    if ((yield self.tb.dut.neighbor_valid[i]) and (yield self.tb.dut.neighbor_ack[i])):
                        neighbor = (yield self.tb.dut.neighbor[i])
                        sender = (yield self.tb.dut.sender_out[i])
                        message = (yield self.tb.dut.message_out[i])
                        num_neighbors = (yield self.tb.dut.num_neighbors_out[i])
                        with self.subTest(sender=sender, neighbor=neighbor):
                            self.assertEqual(sender % 4, i)
                            self.assertEqual(message, sender)
                            self.assertEqual(num_neighbors, len(self.tb.graph[sender]))
                            self.assertIn(neighbor, neighbors[sender])
                            neighbors[sender].remove(neighbor)
                            if not neighbors[sender]:
                                del neighbors[sender]
                        self.assertFalse((yield self.tb.dut.barrier_out[i]))

                yield

        @passive
        def gen_timeout(cycles):
            time = 0
            while time < cycles:
                yield
                time += 1
            self.fail("Timeout (not received: {})".format(neighbors))

        self.run_with([gen_input(), gen_output(), gen_timeout(10000), self.tb.config.platform.getHMCPort(0).gen_responses(self.tb.config.adj_val)], vcd_name="test_neighbors.vcd")

if __name__ == "__main__":
    s = 42
    random.seed(s)
    unittest.main()
