import unittest
import random

from migen import *
from tbsupport import *

from core_neighbors_ddr import NeighborsDDR
from pr.config import Config
from graph_generate import generate_graph


class NeighborCase(SimCase, unittest.TestCase):
    class TestBench(Module):
        def __init__(self):
            _ddr_layout = [
                ("arid", "ID_WIDTH", DIR_M_TO_S),
                ("araddr", "ADDR_WIDTH", DIR_M_TO_S),
                ("arready", 1, DIR_S_TO_M),
                ("arvalid", 1, DIR_M_TO_S),
                ("rid", "ID_WIDTH", DIR_S_TO_M),
                ("rdata", "DATA_WIDTH", DIR_S_TO_M),
                ("rready", 1, DIR_M_TO_S),
                ("rvalid", 1, DIR_S_TO_M)
            ]

            self.graph = generate_graph(num_nodes=15, num_edges=30)
            # print(self.graph)

            self.config = Config(self.graph, nodeidsize=32, edgeidsize=32, peidsize=1, num_pe=1, num_nodes_per_pe=16, max_edges_per_pe=64, use_hmc=False, use_ddr=True, num_channels=3, channel_bits=2)

            self.adj_idx = self.config.adj_idx[0]
            self.port = Record(set_layout_parameters(_ddr_layout, ID_WIDTH=4, ADDR_WIDTH=33, DATA_WIDTH=64*8))
            self.edges_per_burst = 64*8//32
            self.submodules.dut = NeighborsDDR(pe_id=0, config=self.config, port=self.port)



    def test_neighbor(self):
        def gen_input():
            for node in self.tb.graph:
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
            for k in self.tb.graph:
                neighbors[k] = self.tb.graph[k].copy()
            while neighbors:
                yield self.tb.dut.neighbor_out.ack.eq(random.choice([0,1]))
                if ((yield self.tb.dut.neighbor_out.valid) and (yield self.tb.dut.neighbor_out.ack)):
                    neighbor = (yield self.tb.dut.neighbor_out.neighbor)
                    sender = (yield self.tb.dut.neighbor_out.sender)
                    message = (yield self.tb.dut.neighbor_out.message)
                    num_neighbors = (yield self.tb.dut.neighbor_out.num_neighbors)
                    # print("Neighbor {} for sender {} (neighbors = {})".format(neighbor, sender, self.tb.graph[sender]))
                    with self.subTest(node=sender):
                        self.assertEqual(message, sender)
                        self.assertEqual(num_neighbors, len(self.tb.graph[sender]))
                        self.assertIn(neighbor, neighbors[sender])
                        neighbors[sender].remove(neighbor)
                        if not neighbors[sender]:
                            del neighbors[sender]
                yield

        @passive
        def gen_ddr_response():
            inflight_requests = []
            yield self.tb.port.arready.eq(1)
            yield self.tb.port.rvalid.eq(0)
            while True:
                if (yield self.tb.port.rready):
                    if inflight_requests: # and random.choice([True, False])
                        tag, addr = inflight_requests[0]
                        inflight_requests.pop(0)
                        idx = addr // 4
                        data = 0
                        for i in reversed(range(self.tb.edges_per_burst)):
                            data = (data << 32) | self.tb.config.adj_val[idx + i]
                        yield self.tb.port.rdata.eq(data)
                        yield self.tb.port.rid.eq(tag)
                        yield self.tb.port.rvalid.eq(1)
                    else:
                        yield self.tb.port.rvalid.eq(0)
                yield
                if (yield self.tb.port.arready) and (yield self.tb.port.arvalid):
                    inflight_requests.append(((yield self.tb.port.arid), (yield self.tb.port.araddr)))

        @passive
        def gen_timeout(cycles):
            time = 0
            while time < cycles:
                yield
                time += 1
            self.fail("Timeout")

        self.run_with([gen_input(), gen_output(), gen_ddr_response(), gen_timeout(1000)], vcd_name="test_neighbors.vcd")

if __name__ == "__main__":
    s = 42
    random.seed(s)
    unittest.main()
