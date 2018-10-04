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

            num_pe = 2

            config = configparser.ConfigParser()
            config['arch'] = { "num_pe": num_pe }
            config['graph'] = { "nodes": "15", "edges":"30" }
            config['app'] = { "algo": "pr" }
            config['logging'] = {}

            _, self.config = resolve_defaults(args=parse_cmd_args(['sim']), config=config, inverted=True)

            self.submodules.dut = [Neighbors(pe_id=i, config=self.config) for i in range(num_pe)]



    def test_neighbor(self):
        def gen_input(pe):
            for node in self.tb.config.adj_dict:
                idx, num = self.tb.config.adj_idx[pe][node]
                neighbors = []
                yield self.tb.dut[pe].neighbor_in.start_idx.eq(idx)
                yield self.tb.dut[pe].neighbor_in.num_neighbors.eq(num)
                yield self.tb.dut[pe].neighbor_in.sender.eq(node)
                yield self.tb.dut[pe].neighbor_in.message.eq(node)
                yield self.tb.dut[pe].neighbor_in.valid.eq(1)
                yield
                while not (yield self.tb.dut[pe].neighbor_in.ack):
                    yield
            yield self.tb.dut[pe].neighbor_in.valid.eq(0)
            yield self.tb.dut[pe].neighbor_in.barrier.eq(1)
            yield
            while not (yield self.tb.dut[pe].neighbor_in.ack):
                yield
            yield self.tb.dut[pe].neighbor_in.barrier.eq(0)
            yield

        def gen_output(pe):
            neighbors = dict()
            for k in self.tb.config.adj_dict:
                nbs = [n for n in self.tb.config.adj_dict[k] if self.tb.config.addresslayout.pe_adr(n)==pe]
                if nbs:
                    neighbors[k] = nbs
            while neighbors:
                yield self.tb.dut[pe].neighbor_out.ack.eq(random.choice([0,1]))
                if ((yield self.tb.dut[pe].neighbor_out.valid) and (yield self.tb.dut[pe].neighbor_out.ack)):
                    neighbor = (yield self.tb.dut[pe].neighbor_out.neighbor)
                    sender = (yield self.tb.dut[pe].neighbor_out.sender)
                    message = (yield self.tb.dut[pe].neighbor_out.message)
                    num_neighbors = (yield self.tb.dut[pe].neighbor_out.num_neighbors)
                    with self.subTest(node=sender):
                        self.assertEqual(message, sender)
                        self.assertEqual(num_neighbors, self.tb.config.adj_idx[pe][sender][1])
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

        generators = [gen_timeout(1000)]
        generators.extend(gen_input(i) for i in range(self.tb.config.addresslayout.num_pe))
        generators.extend(gen_output(i) for i in range(self.tb.config.addresslayout.num_pe))
        self.run_with(generators, vcd_name="test_neighbors_inverted.vcd")

if __name__ == "__main__":
    s = 42
    random.seed(s)
    unittest.main()
