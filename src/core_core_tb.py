"""Simulate PE grid"""

import unittest
import random
import sys
import argparse
import logging

from migen import *
from tbsupport import *
from functools import reduce
from operator import and_

from graph_input import read_graph
from graph_generate import generate_graph

from core_address import AddressLayout
from fifo_plus_network import Network
from core_apply import Apply
from core_scatter import Scatter
from core_neighbors_hmcx4 import Neighborsx4


class Core(Module):
    def __init__(self, config, pe_start, pe_end):
        self.config = config
        self.pe_start = pe_start

        num_local_pe = pe_end - pe_start
        num_pe = self.config.addresslayout.num_pe
        num_nodes_per_pe = self.config.addresslayout.num_nodes_per_pe

        num_nodes = len(config.adj_dict)

        if config.has_edgedata:
            init_edgedata = config.init_edgedata[pe_start:pe_end]
        else:
            init_edgedata = [None for _ in range(num_local_pe)]

        self.submodules.network = Network(config, pe_start, pe_end)
        self.submodules.apply = [Apply(config, i, config.init_nodedata[i] if config.init_nodedata else None) for i in range(pe_start, pe_end)]


        # if config.use_hmc:
        #     if not config.share_mem_port:
        #         self.submodules.scatter = [Scatter(i, config, adj_mat=(config.adj_idx[i], config.adj_val[i]), edge_data=init_edgedata[i], hmc_port=config.platform.getHMCPort(i)) for i in range(num_pe)]
        #     else:
        #         assert(num_pe <= 36)
        #         # assert((num_pe % 4) == 0)
        #         self.submodules.scatter = [Scatter(i, config, adj_mat=(config.adj_idx[i], config.adj_val[i]), edge_data=init_edgedata[i]) for i in range(num_pe)]
        #         self.submodules.neighbors_hmc = [Neighborsx4(pe_id=i*4, config=config, hmc_port=config.platform.getHMCPort(i)) for i in range(9)]
        #         for j in range(4):
        #             for i in range(9):
        #                 n = j*4 + i
        #                 if n < num_pe:
        #                     self.comb += [
        #                         self.scatter[n].get_neighbors.neighbor_in.connect(self.neighbors_hmc[i].neighbor_in[j]),
        #                         self.neighbors_hmc[i].neighbor_out[j].connect(self.scatter[n].get_neighbors.neighbor_out)
        #                     ]
        # else:
        self.submodules.scatter = [Scatter(i, config, adj_mat=(config.adj_idx[i], config.adj_val[i]), edge_data=init_edgedata[i-pe_start]) for i in range(pe_start, pe_end)]

        # connect within PEs
        self.comb += [self.apply[i].scatter_interface.connect(self.scatter[i].scatter_interface) for i in range(num_local_pe)]

        # connect to network
        self.comb += [self.network.apply_interface[i].connect(self.apply[i].apply_interface) for i in range(num_local_pe)]
        self.comb += [self.scatter[i].network_interface.connect(self.network.network_interface[i]) for i in range(num_local_pe)]

        # state of calculation
        self.global_inactive = Signal()
        self.comb += self.global_inactive.eq(reduce(and_, [pe.inactive for pe in self.apply]))

    def gen_barrier_monitor(self, tb):
        logger = logging.getLogger('simulation.barriermonitor')
        num_pe = self.config.addresslayout.num_pe
        num_local_pe = len(self.apply)

        num_cycles = 0
        while not (yield tb.global_inactive):
            num_cycles += 1
            for a in self.apply:
                if ((yield a.apply_interface.valid) and (yield a.apply_interface.ack)):
                    if (yield a.apply_interface.msg.barrier):
                        logger.debug(str(num_cycles) + ": Barrier enters Apply on PE " + str(a.pe_id))
                if (yield a.gatherkernel.valid_in) and (yield a.gatherkernel.ready):
                    if ((yield a.level) - 1) % self.config.addresslayout.num_channels != (yield a.roundpar):
                        logger.warning("{}: received message's parity ({}) does not match current round ({})".format(num_cycles, (yield a.roundpar), (yield a.level)))
                if ((yield a.scatter_interface.barrier) and (yield a.scatter_interface.valid) and (yield a.scatter_interface.ack)):
                    logger.debug(str(num_cycles) + ": Barrier exits Apply on PE " + str(a.pe_id))
            for s in self.scatter:
                if ((yield s.scatter_interface.valid) and (yield s.scatter_interface.ack)):
                    if (yield s.scatter_interface.barrier):
                        logger.debug(str(num_cycles) + ": Barrier enters Scatter on PE " + str(s.pe_id))
                if ((yield s.barrierdistributor.network_interface_in.valid) and (yield s.barrierdistributor.network_interface_in.ack)):
                    if (yield s.barrierdistributor.network_interface_in.msg.barrier):
                        logger.debug(str(num_cycles) + ": Barrier exits Scatter on PE " + str(s.pe_id))
            yield
