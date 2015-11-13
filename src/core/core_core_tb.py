"""Simulate PE grid"""

import unittest
import random

from migen import *
from tbsupport import *
from functools import reduce
from operator import and_

from recordfifo import RecordFIFO
from graph_input import read_graph
from graph_generate import generate_graph

from core_interfaces import Message
from core_address import AddressLayout
from core_arbiter import Arbiter
from core_apply import Apply
from core_scatter import Scatter

import sys
import argparse

from bfs.config import Config

class TB(Module):
    def __init__(self, config):
        self.config = config
        
        self.addresslayout = self.config.addresslayout

        num_pe = self.addresslayout.num_pe
        num_nodes_per_pe = self.addresslayout.num_nodes_per_pe

        self.adj_dict = adj_dict
        num_nodes = len(adj_dict)
        self.addresslayout.const_base = convert_float_to_32b_int(0.15/num_nodes)

        adj_idx, adj_val = self.addresslayout.generate_partition(self.adj_dict)
        init_nodedata = self.config.init_nodedata

        fifos = [[RecordFIFO(layout=Message(**self.addresslayout.get_params()).layout, depth=1024) for _ in range(num_pe)] for _ in range(num_pe)]
        self.submodules.fifos = fifos
        self.submodules.arbiter = [Arbiter(config, fifos[sink]) for sink in range(num_pe)]
        self.submodules.apply = [Apply(config, init_nodedata[num_nodes_per_pe*i:num_nodes_per_pe*(i+1)]) for i in range(num_pe)]
        self.submodules.scatter = [Scatter(config, adj_mat=(adj_idx[i], adj_val[i])) for i in range(num_pe)]

        # connect within PEs
        self.comb += [self.arbiter[i].apply_interface.connect(self.apply[i].apply_interface) for i in range(num_pe)],\
                     [self.apply[i].scatter_interface.connect(self.scatter[i].scatter_interface) for i in range(num_pe)]

        # connect fifos across PEs
        for source in range(num_pe):
            array_dest_id = Array(fifo.din.dest_id for fifo in [fifos[sink][source] for sink in range(num_pe)])
            array_sender = Array(fifo.din.sender for fifo in [fifos[sink][source] for sink in range(num_pe)])
            array_payload = Array(fifo.din.payload for fifo in [fifos[sink][source] for sink in range(num_pe)])
            array_barrier = Array(fifo.din.barrier for fifo in [fifos[sink][source] for sink in range(num_pe)])
            array_we = Array(fifo.we for fifo in [fifos[sink][source] for sink in range(num_pe)])
            array_writable = Array(fifo.writable for fifo in [fifos[sink][source] for sink in range(num_pe)])

            have_barrier = Signal()
            barrier_ack = Array(Signal() for _ in range(num_pe))
            barrier_done = Signal()

            self.comb += barrier_done.eq(reduce(and_, barrier_ack)), have_barrier.eq(self.scatter[source].network_interface.msg.barrier & self.scatter[source].network_interface.valid)

            self.sync += If(have_barrier & ~barrier_done,
                            [barrier_ack[i].eq(barrier_ack[i] | array_writable[i]) for i in range(num_pe)]
                         ).Else(
                            [barrier_ack[i].eq(0) for i in range(num_pe)]
                         )

            sink = Signal(self.addresslayout.peidsize)

            self.comb+= If(have_barrier,
                            [array_barrier[i].eq(1) for i in range(num_pe)],
                            [array_we[i].eq(~barrier_ack[i]) for i in range(num_pe)],
                            self.scatter[source].network_interface.ack.eq(barrier_done)
                        ).Else(
                            sink.eq(self.scatter[source].network_interface.dest_pe),
                            array_dest_id[sink].eq(self.scatter[source].network_interface.msg.dest_id),
                            array_sender[sink].eq(self.scatter[source].network_interface.msg.sender),
                            array_payload[sink].eq(self.scatter[source].network_interface.msg.payload),
                            array_we[sink].eq(self.scatter[source].network_interface.valid),
                            self.scatter[source].network_interface.ack.eq(array_writable[sink])
                        )

        # state of calculation
        self.global_inactive = Signal()
        self.comb += self.global_inactive.eq(reduce(and_, [pe.inactive for pe in self.apply]))


    def gen_input(self):
        num_pe = self.addresslayout.num_pe
        num_nodes_per_pe = self.addresslayout.num_nodes_per_pe

        init_messages = self.config.init_messages

        # print(init_messages)

        start_message = [self.arbiter[i].start_message for i in range(num_pe)]

        for i in range(num_pe):
            yield start_message[i].select.eq(1)
            yield start_message[i].valid.eq(0)

        while init_messages:
            for i in range(num_pe):
                if (yield start_message[i].ack):
                    if i in init_messages:
                        node, message = init_messages[i].pop()
                        yield start_message[i].msg.dest_id.eq(node)
                        yield start_message[i].msg.payload.eq(message)
                        yield start_message[i].msg.barrier.eq(0)
                        yield start_message[i].valid.eq(1)
                        if len(init_messages[i]) == 0:
                            del init_messages[i]
                    else:
                        yield start_message[i].valid.eq(0)
            yield

        for i in range(num_pe):
            yield start_message[i].msg.dest_id.eq(0)
            yield start_message[i].msg.payload.eq(0)
            yield start_message[i].msg.barrier.eq(1)
            yield start_message[i].valid.eq(1)

        barrier_done = [0 for i in range(num_pe)]
        
        while 0 in barrier_done:
            yield
            for i in range(num_pe):
                if (yield start_message[i].ack):
                    yield start_message[i].valid.eq(0)
                    barrier_done[i] = 1

        for i in range(num_pe):
            yield start_message[i].select.eq(0)


    def gen_barrier_monitor(self):
        num_pe = self.addresslayout.num_pe
        num_cycles = 0
        while not (yield tb.global_inactive):
            num_cycles += 1
            for i in range(num_pe):
                if((yield self.apply[i].apply_interface.valid) 
                   and (yield self.apply[i].apply_interface.ack)):
                    if (yield self.apply[i].apply_interface.msg.barrier):
                        print(str(num_cycles) + "\tBarrier enters Apply on PE " + str(i))
                    # else:
                    #     print(str(num_cycles) + "\tMessage for node {} (apply)".format((yield self.apply[i].apply_interface.msg.dest_id)))
                if((yield self.apply[i].scatter_interface.barrier)
                   and (yield self.apply[i].scatter_interface.valid)
                   and (yield self.apply[i].scatter_interface.ack)):
                    print(str(num_cycles) + "\tBarrier exits Apply on PE " + str(i))
                if((yield self.scatter[i].scatter_interface.valid)
                   and (yield self.scatter[i].scatter_interface.ack)):
                    if (yield self.scatter[i].scatter_interface.barrier):
                        print(str(num_cycles) + "\tBarrier enters Scatter on PE " + str(i))
                    # else:
                    #     print(str(num_cycles) + "\tScatter from node {}".format((yield self.scatter[i].scatter_interface.sender)))
                if((yield self.scatter[i].network_interface.valid)
                   and (yield self.scatter[i].network_interface.ack)):
                    if (yield self.scatter[i].network_interface.msg.barrier):
                        print(str(num_cycles) + "\tBarrier exits Scatter on PE " + str(i))
                    # else:
                    #     print(str(num_cycles) + "\tMessage for node {} (scatter)".format((yield self.scatter[i].network_interface.msg.dest_id)))
            yield


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-f', '--from-file', dest='graphfile',
                        help='filename containing graph')
    parser.add_argument('-n', '--nodes', type=int,
                        help='number of nodes to generate')
    parser.add_argument('-e', '--edges', type=int,
                        help='number of edges to generate')
    parser.add_argument('-s', '--seed', type=int,
                        help='seed to initialise random number generator')
    parser.add_argument('--random-walk', action='store_const',
                        const='random_walk', dest='approach',
                        help='use a random-walk generation algorithm (default)')
    parser.add_argument('--naive', action='store_const',
                        const='naive', dest='approach',
                        help='use a naive generation algorithm (slower)')
    parser.add_argument('--partition', action='store_const',
                        const='partition', dest='approach',
                        help='use a partition-based generation algorithm (biased)')
    args = parser.parse_args()
    
    if args.seed:
        s = args.seed
    else:
        s = 42
    random.seed(s)
        
    if args.graphfile:
        graphfile = open(args.graphfile)
        adj_dict = read_graph(graphfile)
    elif args.nodes:
        num_nodes = args.nodes
        if args.edges:
            num_edges = args.edges
        else:
            num_edges = num_nodes - 1
        if args.approach:
            approach = args.approach
        else:
            approach = "random_walk"
        adj_dict = generate_graph(num_nodes, num_edges, approach=approach)
    else:
        parser.print_help()
        exit(-1)

    # print(adj_dict)
    config = Config(adj_dict)
    tb = TB(config)
    generators = []
    generators.extend([tb.gen_input(), tb.gen_barrier_monitor()])
    generators.extend([a.applykernel.gen_selfcheck(tb, quiet=True) for a in tb.apply])
    # generators.extend([s.get_neighbors.gen_selfcheck(tb, adj_dict, quiet=True) for s in tb.scatter])
    # generators.extend([a.gen_selfcheck(tb, quiet=True) for a in tb.arbiter])
    run_simulation(tb, generators)#, vcd_name="tb.vcd")
