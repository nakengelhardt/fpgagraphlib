import unittest
import random

from migen import *
from tbsupport import *
from pico import PicoPlatform

from core_neighbors_hmc import NeighborsHMC
from pr.config import Config
from graph_generate import generate_graph


class NeighborCase(SimCase, unittest.TestCase):
    class TestBench(Module):
        def __init__(self):

            self.graph = generate_graph(num_nodes=15, num_edges=30)
            # print(self.graph)

            self.config = Config(self.graph, nodeidsize=32, edgeidsize=32, peidsize=1, num_pe=1, num_nodes_per_pe=16, max_edges_per_pe=64, pe_groups=1, inter_pe_delay=0, use_hmc=True)
            self.config.platform = PicoPlatform(bus_width=32, stream_width=128)

            self.adj_idx = self.config.adj_idx[0]
            self.submodules.dut = NeighborsHMC(pe_id=0, config=self.config, adj_val=self.config.adj_val[0])



    def test_neighbor(self):
        def gen_input():
            for node in self.tb.graph:
                idx, num = self.tb.adj_idx[node]
                neighbors = []
                yield self.tb.dut.start_idx.eq(idx)
                yield self.tb.dut.num_neighbors.eq(num)
                yield self.tb.dut.sender_in.eq(node)
                yield self.tb.dut.message_in.eq(node)
                yield self.tb.dut.valid.eq(1)
                yield
                while not (yield self.tb.dut.ack):
                    yield
            yield self.tb.dut.valid.eq(0)
            yield self.tb.dut.barrier_in.eq(1)
            yield
            while not (yield self.tb.dut.ack):
                yield
            yield self.tb.dut.barrier_in.eq(0)
            yield

        def gen_output():
            neighbors = dict()
            for k in self.tb.graph:
                neighbors[k] = self.tb.graph[k].copy()
            while neighbors:
                yield self.tb.dut.neighbor_ack.eq(random.choice([0,1]))
                if ((yield self.tb.dut.neighbor_valid) and (yield self.tb.dut.neighbor_ack)):
                    neighbor = (yield self.tb.dut.neighbor)
                    sender = (yield self.tb.dut.sender_out)
                    message = (yield self.tb.dut.message_out)
                    num_neighbors = (yield self.tb.dut.num_neighbors_out)
                    with self.subTest(node=sender):
                        self.assertEqual(message, sender)
                        self.assertEqual(num_neighbors, len(self.tb.graph[sender]))
                        self.assertIn(neighbor, neighbors[sender])
                        neighbors[sender].remove(neighbor)
                        if not neighbors[sender]:
                            del neighbors[sender]
                yield

        @passive
        def gen_timeout(cycles):
            time = 0
            while time < cycles:
                yield
                time += 1
            self.fail("Timeout")

        self.run_with([gen_input(), gen_output(), gen_timeout(10000), self.tb.config.platform.getHMCPort(0).gen_responses(self.tb.config.adj_val)], vcd_name="test_neighbors.vcd")

if __name__ == "__main__":
    s = 42
    random.seed(s)
    unittest.main()
