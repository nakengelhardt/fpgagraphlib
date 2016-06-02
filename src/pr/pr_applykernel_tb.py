import unittest

from migen import *
from tbsupport import *

from pr.pr_applykernel import ApplyKernel
from core_address import AddressLayout
from pr.config import config
from graph_generate import generate_graph
import random


class ApplyKernelCase(SimCase, unittest.TestCase):
    class TestBench(Module):
        def __init__(self):
            self.addresslayout = config()

            num_nodes = self.addresslayout.num_nodes_per_pe - 1

            self.addresslayout.const_base = convert_float_to_32b_int(0.15/num_nodes)

            self.graph = generate_graph(num_nodes=num_nodes, num_edges=2*num_nodes)

            init_nodedata = [0] + [len(self.graph[node]) for node in range(1, num_nodes+1)]

            self.submodules.dut = ApplyKernel(self.addresslayout)


    def test_applykernel(self):
        num_nodes = len(self.tb.graph)

        msg = [(i, convert_float_to_32b_int(random.random())) for i in range(1, num_nodes+1) for _ in range(len(self.tb.graph[i]))] #(dest_id, weight)
        random.shuffle(msg)
        msg.append(('end', 'end'))
        # print("Input messages: " + str(msg))

        expected = [0.0 for i in range(num_nodes + 1)]
        for node, weight in msg[:-1]:
            expected[node] += convert_32b_int_to_float(weight)

        for node in range(1, num_nodes + 1):
            expected[node] = 0.15/num_nodes + 0.85*expected[node]

        nneighbors = [0] + [len(self.tb.graph[node]) for node in range(1, num_nodes+1)]
        nrecvd = [0 for node in range(num_nodes+1)]
        summ = [0 for node in range(num_nodes+1)]


        def gen_input():
            
            currently_active = set()

            node, weight = msg.pop(0)

            yield self.tb.dut.barrier_in.eq(1)
            yield self.tb.dut.valid_in.eq(0)
            yield
            while not (yield self.tb.dut.ready):
                yield
            yield self.tb.dut.barrier_in.eq(0)

            while msg:
                yield self.tb.dut.level_in.eq(3)
                yield self.tb.dut.nodeid_in.eq(node)
                yield self.tb.dut.message_in.weight.eq(weight)
                yield self.tb.dut.state_in.nneighbors.eq(nneighbors[node])
                yield self.tb.dut.state_in.nrecvd.eq(nrecvd[node])
                yield self.tb.dut.state_in.sum.eq(summ[node])
                if node in currently_active:
                    yield self.tb.dut.valid_in.eq(0)
                else:
                    yield self.tb.dut.valid_in.eq(1)
                    currently_active.add(node)
                    node, weight = msg.pop(0)
                yield
                if (yield self.tb.dut.state_valid):
                        nodeid = (yield self.tb.dut.nodeid_out)
                        self.assertEqual(nneighbors[nodeid], (yield self.tb.dut.state_out.nneighbors))
                        nrecvd[nodeid] = (yield self.tb.dut.state_out.nrecvd)
                        summ[nodeid] = (yield self.tb.dut.state_out.sum)
                        currently_active.remove(nodeid)
                while not (yield self.tb.dut.ready):
                    yield
                    if (yield self.tb.dut.state_valid):
                        nodeid = (yield self.tb.dut.nodeid_out)
                        self.assertEqual(nneighbors[nodeid], (yield self.tb.dut.state_out.nneighbors))
                        nrecvd[nodeid] = (yield self.tb.dut.state_out.nrecvd)
                        summ[nodeid] = (yield self.tb.dut.state_out.sum)
                        currently_active.remove(nodeid)

            yield self.tb.dut.valid_in.eq(0)

        def gen_output():
            nodes = list(self.tb.graph.keys())
            while nodes:
                yield self.tb.dut.message_ack.eq(random.choice([0, 1]))
                if (yield self.tb.dut.message_ack):
                    if (yield self.tb.dut.barrier_out):
                        # print("Barrier")
                        pass
                    elif (yield self.tb.dut.message_valid):
                        node = (yield self.tb.dut.message_sender)
                        self.assertIn(node, nodes)
                        nodes.remove(node)
                        weight = convert_32b_int_to_float((yield self.tb.dut.message_out.weight))
                        self.assertAlmostEqual(weight, expected[node], delta=1E-5)
                        # print("({}, {})".format(node, weight))
                yield

        self.run_with([gen_input(), gen_output()], vcd_name="tb.vcd")

                
if __name__ == "__main__":
    random.seed(42)
    unittest.main()