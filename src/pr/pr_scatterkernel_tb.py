import unittest
import random

from migen import *
from tbsupport import *

from pr.pr_scatterkernel import ScatterKernel
from pr.config import config
from graph_generate import generate_graph

class ScatterKernelCase(SimCase, unittest.TestCase):
    class TestBench(Module):
        def __init__(self):
            self.addresslayout = config()

            num_nodes = self.addresslayout.num_nodes_per_pe - 1

            self.graph = generate_graph(num_nodes=num_nodes, num_edges=2*num_nodes)

            # print(self.tb.graph)

            self.submodules.dut = ScatterKernel(self.addresslayout)

    def test_scatterkernel(self):
        num_nodes = len(self.tb.graph)

        msg = [(i, convert_float_to_32b_int(random.random())) for j in range(1, num_nodes+1) for i in self.tb.graph[j]]
        random.shuffle(msg)

        def gen_input():
            for node, weight in msg:
                yield self.tb.dut.message_in.weight.eq(weight)
                yield self.tb.dut.num_neighbors_in.eq(len(self.tb.graph[node]))
                yield self.tb.dut.neighbor_in.eq(node)
                yield self.tb.dut.barrier_in.eq(0)
                yield self.tb.dut.valid_in.eq(1)
                yield
                while not (yield self.tb.dut.valid_in) & (yield self.tb.dut.ready):
                    yield
            yield self.tb.dut.valid_in.eq(0)

            for _ in range(110):
                yield

        def gen_output():
            nrecvd = 0
            while nrecvd < len(msg):
                yield self.tb.dut.message_ack.eq(random.choice([0,1]))
                if (yield self.tb.dut.message_ack):
                    if (yield self.tb.dut.barrier_out):
                        # print("Barrier")
                        pass
                    elif (yield self.tb.dut.valid_out):
                        neighbor_out = (yield self.tb.dut.neighbor_out)
                        weight = convert_32b_int_to_float((yield self.tb.dut.message_out.weight))
                        # print("Message: ({}, {})".format(selfp.sk.neighbor_out, _32b_int_to_float(selfp.sk.message_out.weight)))
                        exp_node, exp_weight = msg[nrecvd]
                        self.assertEqual(neighbor_out, exp_node)
                        self.assertAlmostEqual(weight, convert_32b_int_to_float(exp_weight)/len(self.tb.graph[neighbor_out]))
                        nrecvd += 1
                yield

        self.run_with([gen_input(), gen_output()], vcd_name="tb.vcd")

if __name__ == "__main__":
    s = 42
    random.seed(s)
    print("Random seed: " + str(s))
    unittest.main()
