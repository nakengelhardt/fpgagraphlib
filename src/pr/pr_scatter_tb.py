import unittest
import random

from migen import *
from tbsupport import *

from pr_scatter import PRScatter
from pr_address import PRAddressLayout
from pr_config import config
from pr_graph_generate import generate_graph


class ScatterCase(SimCase, unittest.TestCase):
    class TestBench(Module):
        def __init__(self):

            self.addresslayout = config()

            num_nodes = self.addresslayout.num_nodes_per_pe - 1

            self.graph = generate_graph(num_nodes=num_nodes, num_edges=2*num_nodes)
            print(self.graph)

            adj_idx, adj_val = self.addresslayout.generate_partition(self.graph)

            self.submodules.dut = PRScatter(self.addresslayout, adj_mat=(adj_idx[0], adj_val[0]))

    def test_scatter(self):
        num_nodes = len(self.tb.graph)

        msg = [(i, convert_float_to_32b_int(random.random())) for i in range(1, num_nodes+1)]
        random.shuffle(msg)

        expected = [(j, convert_32b_int_to_float(w)/len(self.tb.graph[i])) for i, w in msg for j in self.tb.graph[i]]

        def gen_input():
            for sender, message in msg:
                print("Sending: {}, {}".format(sender, convert_32b_int_to_float(message)))
                yield self.tb.dut.scatter_interface.msg.eq(message)
                yield self.tb.dut.scatter_interface.sender.eq(sender)
                yield self.tb.dut.scatter_interface.valid.eq(1)
                yield
                while not (yield self.tb.dut.scatter_interface.ack):    
                    yield
            yield self.tb.dut.scatter_interface.valid.eq(0)
            yield

        def gen_output():
            nrecvd = 0
            while nrecvd < len(expected):
                yield self.tb.dut.network_interface.ack.eq(random.choice([1]))
                yield
                if (yield self.tb.dut.network_interface.valid) & (yield self.tb.dut.network_interface.ack):
                    if (yield self.tb.dut.network_interface.barrier):
                        # print("Barrier")
                        pass
                    else:
                        dest = (yield self.tb.dut.network_interface.msg.dest_id)
                        pe = (yield self.tb.dut.network_interface.msg.dest_pe)
                        weight = convert_32b_int_to_float((yield self.tb.dut.network_interface.msg.payload))
                        exp_dest, exp_weight = expected[nrecvd]
                        self.assertEqual(dest, exp_dest)
                        self.assertAlmostEqual(weight, exp_weight, delta=1E-5)
                        print("Receiving: {}, {}".format(dest, weight))
                        nrecvd += 1
            yield self.tb.dut.network_interface.ack.eq(1)
            yield

        self.run_with([gen_input(), gen_output()], vcd_name="tb.vcd", signal_problematique=self.tb.dut.scatterkernel.ready)


                
if __name__ == "__main__":
    s = 42
    random.seed(s)
    print("Random seed: " + str(s))
    unittest.main()

