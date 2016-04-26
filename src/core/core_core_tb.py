"""Simulate PE grid"""

import unittest
import random

from migen import *
from tbsupport import *
from functools import reduce
from operator import and_

from graph_input import read_graph
from graph_generate import generate_graph

from core_address import AddressLayout
from core_network import Network
from core_apply import Apply
from core_scatter import Scatter
from core_neighbors_hmcx4 import Neighborsx4

import sys
import argparse

class Core(Module):
    def __init__(self, config):
        self.config = config

        self.addresslayout = self.config.addresslayout

        num_pe = self.addresslayout.num_pe
        num_nodes_per_pe = self.addresslayout.num_nodes_per_pe

        num_nodes = len(config.adj_dict)

        if config.has_edgedata:
            init_edgedata = config.init_edgedata
        else:
            init_edgedata = [None for _ in range(num_pe)]

        self.submodules.network = Network(config)
        self.submodules.apply = [Apply(config, config.init_nodedata[num_nodes_per_pe*i:num_nodes_per_pe*(i+1)] if config.init_nodedata else None)  for i in range(num_pe)]
        self.submodules.scatter = [Scatter(config, adj_mat=(config.adj_idx[i], config.adj_val[i]), edge_data=init_edgedata[i]) for i in range(num_pe)]

        if hasattr(config, "platform"):
            assert(num_pe <= 36)
            assert((num_pe % 4) == 0)
            self.submodules.neighbors_hmc = [Neighborsx4(config, config.platform.getHMCPort(i)) for i in range(9)]
            for i in range(9):
                for j in range(4):
                    n = i*4 + j
                    if n < num_pe:
                        self.comb += [
                            self.neighbors_hmc[i].start_idx[j].eq(self.scatter[n].get_neighbors.start_idx),
                            self.neighbors_hmc[i].num_neighbors[j].eq(self.scatter[n].get_neighbors.num_neighbors),
                            self.neighbors_hmc[i].barrier_in[j].eq(self.scatter[n].get_neighbors.barrier_in),
                            self.neighbors_hmc[i].message_in[j].eq(self.scatter[n].get_neighbors.message_in),
                            self.neighbors_hmc[i].sender_in[j].eq(self.scatter[n].get_neighbors.sender_in),
                            self.neighbors_hmc[i].round_in[j].eq(self.scatter[n].get_neighbors.round_in),
                            self.neighbors_hmc[i].valid[j].eq(self.scatter[n].get_neighbors.valid),
                            self.scatter[n].get_neighbors.ack.eq(self.neighbors_hmc[i].ack[j]),

                            self.scatter[n].get_neighbors.neighbor.eq(self.neighbors_hmc[i].neighbor[j]),
                            self.scatter[n].get_neighbors.barrier_out.eq(self.neighbors_hmc[i].barrier_out[j]),
                            self.scatter[n].get_neighbors.message_out.eq(self.neighbors_hmc[i].message_out[j]),
                            self.scatter[n].get_neighbors.sender_out.eq(self.neighbors_hmc[i].sender_out[j]),
                            self.scatter[n].get_neighbors.round_out.eq(self.neighbors_hmc[i].round_out[j]),
                            self.scatter[n].get_neighbors.num_neighbors_out.eq(self.neighbors_hmc[i].num_neighbors_out[j]),
                            self.scatter[n].get_neighbors.neighbor_valid.eq(self.neighbors_hmc[i].neighbor_valid[j]),
                            self.neighbors_hmc[i].neighbor_ack[j].eq(self.scatter[n].get_neighbors.neighbor_ack)
                        ]


        # connect within PEs
        self.comb += [self.apply[i].scatter_interface.connect(self.scatter[i].scatter_interface) for i in range(num_pe)]

        # connect to network
        self.comb += [self.network.apply_interface[i].connect(self.apply[i].apply_interface) for i in range(num_pe)]
        self.comb += [self.scatter[i].network_interface.connect(self.network.network_interface[i]) for i in range(num_pe)]

        # state of calculation
        self.global_inactive = Signal()
        self.comb += self.global_inactive.eq(reduce(and_, [pe.inactive for pe in self.apply]))


    def gen_input(self):
        num_pe = self.addresslayout.num_pe
        num_nodes_per_pe = self.addresslayout.num_nodes_per_pe

        init_messages = self.config.init_messages

        # print(init_messages)

        start_message = [self.network.arbiter[i].start_message for i in range(num_pe)]

        for i in range(num_pe):
            yield start_message[i].select.eq(1)
            yield start_message[i].valid.eq(0)

        while [x for l in init_messages for x in l]:
            for i in range(num_pe):
                if (yield start_message[i].ack):
                    if init_messages[i]:
                        message = init_messages[i].pop()
                        yield start_message[i].msg.dest_id.eq(message['dest_id'])
                        yield start_message[i].msg.sender.eq(message['sender'])
                        yield start_message[i].msg.payload.eq(message['payload'])
                        yield start_message[i].msg.roundpar.eq(1)
                        yield start_message[i].msg.barrier.eq(0)
                        yield start_message[i].valid.eq(1)
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
        while not (yield self.global_inactive):
            num_cycles += 1
            for i in range(num_pe):
                if ((yield self.apply[i].apply_interface.valid)
                    and (yield self.apply[i].apply_interface.ack)):
                    if (yield self.apply[i].apply_interface.msg.barrier):
                        print(str(num_cycles) + "\tBarrier enters Apply on PE " + str(i))
                    # else:
                    #     print(str(num_cycles) + "\tMessage for node {} (apply)".format((yield self.apply[i].apply_interface.msg.dest_id)))
                if ((yield self.apply[i].applykernel.valid_in)
                    and (yield self.apply[i].applykernel.ready)
                    and not (yield self.apply[i].applykernel.barrier_in)):
                    if (yield self.apply[i].level) % 2 == (yield self.apply[i].roundpar):
                        print("{}\tWarning: received message's parity ({}) does not match current round ({})".format(num_cycles, (yield self.apply[i].roundpar), (yield self.apply[i].level)))
                if ((yield self.apply[i].scatter_interface.barrier)
                    and (yield self.apply[i].scatter_interface.valid)
                    and (yield self.apply[i].scatter_interface.ack)):
                    print(str(num_cycles) + "\tBarrier exits Apply on PE " + str(i))
                if ((yield self.scatter[i].scatter_interface.valid)
                    and (yield self.scatter[i].scatter_interface.ack)):
                    if (yield self.scatter[i].scatter_interface.barrier):
                        print(str(num_cycles) + "\tBarrier enters Scatter on PE " + str(i))
                    # else:
                    #     print(str(num_cycles) + "\tScatter from node {}".format((yield self.scatter[i].scatter_interface.sender)))
                if ((yield self.scatter[i].network_interface.valid)
                    and (yield self.scatter[i].network_interface.ack)):
                    if (yield self.scatter[i].network_interface.msg.barrier):
                        print(str(num_cycles) + "\tBarrier exits Scatter on PE " + str(i))
                    # else:
                    #     print(str(num_cycles) + "\tMessage for node {} (scatter)".format((yield self.scatter[i].network_interface.msg.dest_id)))
            yield

    def gen_network_stats(self):
        num_cycles = 0
        with open("{}.net_stats.{}pe.{}groups.{}delay.log".format(self.config.name, self.config.addresslayout.num_pe, self.config.addresslayout.pe_groups, self.config.addresslayout.inter_pe_delay), 'w') as netstatsfile:
            netstatsfile.write("Cycle\tNumber of messages sent\n")
            while not (yield self.global_inactive):
                num_cycles += 1
                num_msgs = 0
                for scatter in self.scatter:
                    if (yield scatter.network_interface.valid) and (yield scatter.network_interface.ack):
                        num_msgs += 1
                netstatsfile.write("{}\t{}\n".format(num_cycles, num_msgs))
                yield
