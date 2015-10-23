import unittest
import random

from migen import *
from tbsupport import *

from pr_neighbors import PRNeighbors
from pr_address import PRAddressLayout
from pr_config import config
from pr_graph_generate import generate_graph


class NeighborCase(SimCase, unittest.TestCase):
    class TestBench(Module):
        def __init__(self):

            self.addresslayout = config()

            num_nodes = self.addresslayout.num_nodes_per_pe - 1

            self.graph = generate_graph(num_nodes=num_nodes, num_edges=2*num_nodes)
            print(self.graph)

            adj_idx, adj_val = self.addresslayout.generate_partition(self.graph)
            self.adj_idx = adj_idx[0]
            self.submodules.dut = PRNeighbors(addresslayout=self.addresslayout, adj_val=adj_val[0])

            self.curr_node = Signal(self.addresslayout.nodeidsize)

    def test_neighbor(self):
        
        self.done = False
        def gen_input():
            yield self.tb.curr_node.eq(0)
            for node in self.tb.graph:
                idx, num = self.tb.adj_idx[node]
                neighbors = []
                yield self.tb.dut.start_idx.eq(idx)
                yield self.tb.dut.num_neighbors.eq(num)
                yield self.tb.dut.valid.eq(1)
                yield
                while not (yield self.tb.dut.ack):
                    yield
                yield self.tb.curr_node.eq(node)
            yield self.tb.dut.valid.eq(0)
            yield
            while not (yield self.tb.dut.ack):
                yield
            yield
            self.done = True

        def gen_output():
            neighbors = self.tb.graph.copy()
            while not self.done:
                yield self.tb.dut.neighbor_ack.eq(random.choice([1]))
                if ((yield self.tb.dut.neighbor_valid) and (yield self.tb.dut.neighbor_ack)):
                    neighbor = (yield self.tb.dut.neighbor)
                    curr_node = (yield self.tb.curr_node)
                    with self.subTest(node=curr_node):
                        self.assertIn(neighbor, neighbors[curr_node])
                        neighbors[curr_node].remove(neighbor)
                        if not neighbors[curr_node]:
                            del neighbors[curr_node]
                yield


        self.run_with([gen_input(), gen_output()])#, vcd_name="tb.vcd")

if __name__ == "__main__":
    s = 42
    random.seed(s)
    unittest.main()