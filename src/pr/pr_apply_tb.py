import unittest

from migen import *
from tbsupport import *

from pr_apply import PRApply
from pr_address import PRAddressLayout
from pr_config import config
from pr_graph_generate import generate_graph
from random import random, shuffle, choice, seed


class ApplyCase(SimCase, unittest.TestCase):
    class TestBench(Module):
        def __init__(self):
            self.addresslayout = config()

            num_nodes = self.addresslayout.num_nodes_per_pe - 1

            self.addresslayout.const_base = convert_float_to_32b_int(0.15/num_nodes)

            self.graph = generate_graph(num_nodes=num_nodes, num_edges=2*num_nodes)

            init_nodedata = [0] + [len(self.graph[node]) for node in range(1, num_nodes+1)]

            self.submodules.dut = PRApply(self.addresslayout, init_nodedata=init_nodedata)


    def test_apply(self):
        num_nodes = len(self.tb.graph)

        msg = [(i, convert_float_to_32b_int(random())) for i in range(1, num_nodes+1) for _ in range(len(self.tb.graph[i]))] #(dest_id, weight)

        # print("Input messages: " + str(msg))

        expected = [0.0 for i in range(num_nodes + 1)]
        for node, weight in msg:
            expected[node] += convert_32b_int_to_float(weight)

        # print("Expected output: ")
        for node in range(1, num_nodes + 1):
            expected[node] = 0.15/num_nodes + 0.85*expected[node]
            # print("{}: {}".format(node, expected[node]))

        testce = [1] #[0, 1]

        def gen_input():
            # increase level to 1
            yield self.tb.dut.apply_interface.msg.barrier.eq(1)
            yield self.tb.dut.apply_interface.valid.eq(1)
            yield
            while not (yield self.tb.dut.apply_interface.ack):
                yield

            for test in range(4):
                # missing : test init
                # run 1: send one by one to avoid collisions
                # run 2: send all at once to test collision handling
                # run 3: shuffle messages
                # run 4: increase level past 30, check no more messages sent

                # print("### starting run " + str(test) + " ###")

                if test == 2:
                    shuffle(msg)

                # raise level to test cutoff
                if test == 3:
                    yield self.tb.dut.apply_interface.msg.barrier.eq(1)
                    yield self.tb.dut.apply_interface.valid.eq(1)
                    while (yield self.tb.dut.level) < 30:
                        yield

                # print(msg)

                msgs_sent = 0
                scatter = []
                while msgs_sent < len(msg):
                    # input
                    a, b = msg[msgs_sent]
                    yield self.tb.dut.apply_interface.msg.dest_id.eq(a)
                    yield self.tb.dut.apply_interface.msg.payload.eq(b)
                    yield self.tb.dut.apply_interface.msg.barrier.eq(0)
                    yield self.tb.dut.apply_interface.valid.eq(1)
                    yield

                    # check for input success
                    if (yield self.tb.dut.apply_interface.ack):
                        msgs_sent += 1
                        if test==0:
                            yield self.tb.dut.apply_interface.valid.eq(0)
                            for _ in range(20):
                                yield

                yield self.tb.dut.apply_interface.msg.barrier.eq(1)
                yield self.tb.dut.apply_interface.valid.eq(1)
                yield
                while not (yield self.tb.dut.apply_interface.ack):
                    yield

                # done sending
                yield self.tb.dut.apply_interface.valid.eq(0)
                

        def gen_output():
            num_barrier = 0
            recvd_since_last_barrier = []
            while True:
                # output
                # test pipeline stall: only sometimes ack
                ack = choice(testce)
                yield self.tb.dut.scatter_interface.ack.eq(ack)
                yield
                if (yield self.tb.dut.scatter_interface.valid) & (yield self.tb.dut.scatter_interface.ack):
                    if (yield self.tb.dut.scatter_interface.barrier):
                        recvd_since_last_barrier = []
                        # print("Barrier")
                        num_barrier += 1
                        if num_barrier == 31:
                            break
                    else:
                        sender = (yield self.tb.dut.scatter_interface.sender)
                        self.assertNotIn(sender, recvd_since_last_barrier)
                        weight = convert_32b_int_to_float((yield self.tb.dut.scatter_interface.msg))
                        # self.assertAlmostEqual(weight, expected[sender], delta=1E-6)
                        recvd_since_last_barrier.append(sender)

                        # print("ScatterInterface: message = sender: {}, weight: {}".format(sender, weight))
            for _ in range(100):
                yield
                self.assertFalse((yield self.tb.dut.scatter_interface.valid) and not (yield self.tb.dut.scatter_interface.barrier))
        
                    

        self.run_with([gen_input(), gen_output()], vcd_name="tb.vcd")


if __name__ == "__main__":
    s = 23
    seed(s)
    print("Random seed: " + str(s))
    unittest.main()
