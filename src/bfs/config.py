from migen import *

from core_address import AddressLayout
from bfs.interfaces import node_storage_layout
from bfs.applykernel import ApplyKernel
from bfs.scatterkernel import ScatterKernel

import logging

class Config:
    def __init__(self, adj_dict):
        self.name = "bfs"
        logger = logging.getLogger('config')

        # nodeidsize = 32
        # num_nodes_per_pe = 2**11
        # edgeidsize = 32
        # max_edges_per_pe = 2**13
        # num_pe = 9
        # peidsize = bits_for(num_pe)

        # nodeidsize = 16
        # num_nodes_per_pe = 2**13
        # edgeidsize = 16
        # max_edges_per_pe = 2**15
        # peidsize = 1
        # num_pe = 1
        # pe_groups = 4
        # inter_pe_delay = 256

        # nodeidsize = 16
        # num_nodes_per_pe = 2**10
        # edgeidsize = 16
        # max_edges_per_pe = 2**12
        # peidsize = 5
        # num_pe = 32

        # nodeidsize = 16
        # num_nodes_per_pe = 2**8
        # edgeidsize = 16
        # max_edges_per_pe = 2**12
        # peidsize = 8
        # num_pe = 8

        nodeidsize = 32
        num_nodes_per_pe = 2**4
        edgeidsize = 32
        max_edges_per_pe = 2**6
        peidsize = 4
        num_pe = 2

        pe_groups = 1
        inter_pe_delay = 0

        payloadsize = nodeidsize

        self.addresslayout = AddressLayout(nodeidsize=nodeidsize, edgeidsize=edgeidsize, peidsize=peidsize, num_pe=num_pe, num_nodes_per_pe=num_nodes_per_pe, max_edges_per_pe=max_edges_per_pe, payloadsize=payloadsize)
        self.addresslayout.node_storage_layout_len = layout_len(set_layout_parameters(node_storage_layout, **self.addresslayout.get_params()))
        self.addresslayout.pe_groups = pe_groups
        self.addresslayout.inter_pe_delay = inter_pe_delay

        self.use_hmc = True

        self.adj_dict = adj_dict
        if self.use_hmc:
            adj_idx, adj_val = self.addresslayout.generate_partition_flat(self.adj_dict)
        else:
            adj_idx, adj_val = self.addresslayout.generate_partition(self.adj_dict)
        self.adj_idx = adj_idx
        self.adj_val = adj_val

        self.has_edgedata = False

        self.applykernel = ApplyKernel
        self.scatterkernel = ScatterKernel

        self.init_nodedata = None

        self.init_messages = [list() for _ in range(num_pe)]
        self.init_messages[0].append({'dest_id':1, 'sender':1, 'payload':0})

        logger.info("Algorithm: BFS")
        logger.info("Using HMC: " + "YES" if self.use_hmc else "NO")
        logger.info("nodeidsize = {}".format(nodeidsize))
        logger.info("edgeidsize = {}".format(edgeidsize))
        logger.info("peidsize = {}".format(peidsize))
        logger.info("num_pe = " + str(num_pe))
        logger.info("num_nodes_per_pe = " + str(num_nodes_per_pe))
        logger.info("max_edges_per_pe = " + str(max_edges_per_pe))
        logger.info("inter_pe_delay =" + str(inter_pe_delay))
