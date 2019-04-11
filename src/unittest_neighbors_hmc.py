import unittest
import random
import configparser

from migen import *
from tbsupport import convert_record_to_int, SimCase
from pico import PicoPlatform

from core_neighbors_hmc_ordered import NeighborsHMC
from core_init import resolve_defaults, parse_cmd_args


class NeighborCase(SimCase, unittest.TestCase):
    class TestBench(Module):
        def __init__(self):

            config = configparser.ConfigParser()
            config['arch'] = { "num_pe": "1", "use_hmc": True}
            config['graph'] = { "nodes": "15", "edges":"30" }
            config['app'] = { "algo": "sssp" }
            config['logging'] = {"disable_logfile" : True }

            self.config = resolve_defaults(config=config, inverted=False)

            self.adj_idx = self.config.adj_idx[0]



            self.config.platform = PicoPlatform(1, bus_width=32, stream_width=128, init=self.config.adj_val, init_elem_size_bytes=self.config.addresslayout.adj_val_entry_size_in_bytes)
            self.submodules.dut = NeighborsHMC(pe_id=0, config=self.config)



    def test_neighbor(self):
        print(self.tb.config.adj_dict)
        def gen_input():
            yield self.tb.dut.neighbor_in.barrier.eq(0)
            for node in self.tb.config.adj_dict:
                idx, num = self.tb.adj_idx[node]
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
                self.assertFalse((yield self.tb.dut.neighbor_out.barrier))
                if ((yield self.tb.dut.neighbor_out.valid) and (yield self.tb.dut.neighbor_out.ack)):
                    neighbor = (yield self.tb.dut.neighbor_out.neighbor)
                    sender = (yield self.tb.dut.neighbor_out.sender)
                    message = (yield self.tb.dut.neighbor_out.message)
                    num_neighbors = (yield self.tb.dut.neighbor_out.num_neighbors)
                    if self.tb.config.has_edgedata:
                        edgedata = (yield self.tb.dut.edgedata_out)
                    self.assertEqual(message, sender, "Message passthrough incorrect (sender={}, neighbor={}, message={})".format(sender, neighbor, message))
                    self.assertEqual(num_neighbors, len(self.tb.config.adj_dict[sender]), "num_neighbors incorrect (sender={}, neighbor={}, num_neighbors={})".format(sender, neighbor, num_neighbors))
                    self.assertIn(neighbor, neighbors[sender], "Neighbor {} not expected ({})".format(neighbor, "already seen" if neighbor in self.tb.config.adj_dict[sender] else "not a neighbor of {}".format(sender)))
                    if self.tb.config.has_edgedata:
                        expected_edgedata = convert_record_to_int(self.tb.config.addresslayout.edge_storage_layout, **self.tb.config.graph.get_edge_data(sender, neighbor))
                        self.assertEqual(edgedata, expected_edgedata, "Wrong edgedata")
                    neighbors[sender].remove(neighbor)
                    if not neighbors[sender]:
                        del neighbors[sender]
                yield
            while not (yield self.tb.dut.neighbor_out.barrier):
                yield

        @passive
        def gen_timeout(cycles):
            time = 0
            while time < cycles:
                yield
                time += 1
            self.fail("Timeout")

        generators = self.tb.config.platform.getSimGenerators()
        generators['sys'].extend([gen_input(), gen_output(), gen_timeout(1000)])
        self.run_with(generators['sys'], vcd_name="test_neighbors.vcd")

if __name__ == "__main__":
    s = 42
    random.seed(s)
    unittest.main()
