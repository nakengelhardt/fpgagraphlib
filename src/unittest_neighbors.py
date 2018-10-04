import unittest
import random
import configparser

from migen import *
from tbsupport import *

from core_neighbors import Neighbors
from core_init import resolve_defaults, parse_cmd_args


class NeighborCase(SimCase, unittest.TestCase):
    class TestBench(Module):
        def __init__(self):

            config = configparser.ConfigParser()
            config['arch'] = { "num_pe": "1" }
            config['graph'] = { "nodes": "15", "edges":"30" }
            config['app'] = { "algo": "pr" }
            config['logging'] = {}

            _, self.config = resolve_defaults(args=parse_cmd_args(['sim']), config=config, inverted=False)

            # self.graph, ids = generate_graph(num_nodes=15, num_edges=30)
            # print(self.graph)

            # self.config = Config(self.graph, nodeidsize=32, edgeidsize=32, peidsize=2, num_pe=2, num_nodes_per_pe=16, max_edges_per_pe=64, num_channels=4, channel_bits=2)

            self.adj_idx = self.config.adj_idx[0]
            self.submodules.dut = Neighbors(pe_id=0, config=self.config)



    def test_neighbor(self):
        def gen_input():
            for node in self.tb.config.adj_dict:
                idx, num = self.tb.adj_idx[node]
                neighbors = []
                yield self.tb.dut.neighbor_in.start_idx.eq(idx)
                yield self.tb.dut.neighbor_in.num_neighbors.eq(num)
                yield self.tb.dut.neighbor_in.sender.eq(node)
                yield self.tb.dut.neighbor_in.message.eq(node)
                yield self.tb.dut.neighbor_in.valid.eq(1)
                yield
                while not (yield self.tb.dut.neighbor_in.ack):
                    yield
            yield self.tb.dut.neighbor_in.valid.eq(0)
            yield self.tb.dut.neighbor_in.barrier.eq(1)
            yield
            while not (yield self.tb.dut.neighbor_in.ack):
                yield
            yield self.tb.dut.neighbor_in.barrier.eq(0)
            yield

        def gen_output():
            neighbors = dict()
            for k in self.tb.config.adj_dict:
                neighbors[k] = self.tb.config.adj_dict[k].copy()
            while neighbors:
                yield self.tb.dut.neighbor_out.ack.eq(random.choice([0,1]))
                if ((yield self.tb.dut.neighbor_out.valid) and (yield self.tb.dut.neighbor_out.ack)):
                    neighbor = (yield self.tb.dut.neighbor_out.neighbor)
                    sender = (yield self.tb.dut.neighbor_out.sender)
                    message = (yield self.tb.dut.neighbor_out.message)
                    num_neighbors = (yield self.tb.dut.neighbor_out.num_neighbors)
                    with self.subTest(node=sender):
                        self.assertEqual(message, sender)
                        self.assertEqual(num_neighbors, len(self.tb.config.adj_dict[sender]))
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

        self.run_with([gen_input(), gen_output(), gen_timeout(10000)], vcd_name="test_neighbors.vcd")

if __name__ == "__main__":
    s = 42
    random.seed(s)
    unittest.main()
