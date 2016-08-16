from migen import *

from core_address import AddressLayout
from bfs.interfaces import node_storage_layout
from bfs.applykernel import ApplyKernel
from bfs.scatterkernel import ScatterKernel

import logging

class Config:
    def __init__(self, adj_dict, use_hmc=False, **kwargs):
        self.name = "bfs"
        logger = logging.getLogger('config')

        payloadsize = kwargs['nodeidsize']

        self.addresslayout = AddressLayout(payloadsize=payloadsize, **kwargs)
        self.addresslayout.node_storage_layout_len = layout_len(set_layout_parameters(node_storage_layout, **self.addresslayout.get_params()))

        self.use_hmc = use_hmc

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

        self.init_messages = [list() for _ in range(self.addresslayout.num_pe)]
        self.init_messages[0].append({'dest_id':1, 'sender':1, 'payload':0})

        logger.info("Algorithm: BFS")
        logger.info("Using HMC: " + "YES" if self.use_hmc else "NO")
        logger.info("nodeidsize = {}".format(self.addresslayout.nodeidsize))
        logger.info("edgeidsize = {}".format(self.addresslayout.edgeidsize))
        logger.info("peidsize = {}".format(self.addresslayout.peidsize))
        logger.info("num_pe = " + str(self.addresslayout.num_pe))
        logger.info("num_nodes_per_pe = " + str(self.addresslayout.num_nodes_per_pe))
        logger.info("max_edges_per_pe = " + str(self.addresslayout.max_edges_per_pe))
        logger.info("inter_pe_delay =" + str(self.addresslayout.inter_pe_delay))
