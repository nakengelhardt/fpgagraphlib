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

            self.config = Config(self.graph, nodeidsize=32, edgeidsize=32, peidsize=1, num_pe=1, num_nodes_per_pe=16, max_edges_per_pe=64, use_hmc=True, num_channels=4, channel_bits=2)
            self.config.platform = PicoPlatform(1, bus_width=32, stream_width=128)

            self.adj_idx = self.config.adj_idx[0]
            self.submodules.dut = Neighborsx4(pe_id=0, config=self.config)



    def test_neighbor(self):
        def gen_input():
            for node in self.tb.graph:
                idx, num = self.tb.adj_idx[node]
                neighbors = []
                for n in self.tb.dut.neighbor_in:
                    yield n.valid.eq(0)
                pe = node % 4
                yield self.tb.dut.neighbor_in[pe].start_idx.eq(idx)
                yield self.tb.dut.neighbor_in[pe].num_neighbors.eq(num)
                yield self.tb.dut.neighbor_in[pe].sender.eq(node)
                yield self.tb.dut.neighbor_in[pe].message.eq(node)
                yield self.tb.dut.neighbor_in[pe].valid.eq(1)
                yield
                while not (yield self.tb.dut.neighbor_in[pe].ack):
                    yield
            for n in self.tb.dut.neighbor_in:
                yield n.valid.eq(0)
            for n in self.tb.dut.neighbor_in:
                yield n.barrier.eq(1)
            yield
            ack = [False for _ in range(4)]
            while not (ack[0] and ack[1] and ack[2] and ack[3]):
                for i in range(4):
                    if (yield self.tb.dut.neighbor_in[i].ack):
                        ack[i] = True
                        yield self.tb.dut.neighbor_in[i].barrier.eq(0)
                yield
            yield

        neighbors = dict()
        def gen_output():
            for k in self.tb.graph:
                neighbors[k] = self.tb.graph[k].copy()
            while neighbors:
                for i in range(4):
                    yield self.tb.dut.neighbor_out[i].ack.eq(random.choice([0,1]))
                    if ((yield self.tb.dut.neighbor_out[i].valid) and (yield self.tb.dut.neighbor_out[i].ack)):
                        neighbor = (yield self.tb.dut.neighbor_out[i].neighbor)
                        sender = (yield self.tb.dut.neighbor_out[i].sender)
                        message = (yield self.tb.dut.neighbor_out[i].message)
                        num_neighbors = (yield self.tb.dut.neighbor_out[i].num_neighbors)
                        with self.subTest(sender=sender, neighbor=neighbor):
                            self.assertEqual(sender % 4, i)
                            self.assertEqual(message, sender)
                            self.assertEqual(num_neighbors, len(self.tb.graph[sender]))
                            self.assertIn(neighbor, neighbors[sender])
                            neighbors[sender].remove(neighbor)
                            if not neighbors[sender]:
                                del neighbors[sender]
                        self.assertFalse((yield self.tb.dut.neighbor_out[i].barrier))

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
