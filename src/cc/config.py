from migen import *

from core_address import AddressLayout
from cc.interfaces import node_storage_layout
from cc.applykernel import ApplyKernel
from cc.scatterkernel import ScatterKernel

import logging

class Config:
    def __init__(self, adj_dict, use_hmc=False, **kwargs):
        self.name = "cc"
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
        self.use_hmc = use_hmc

        self.applykernel = ApplyKernel
        self.scatterkernel = ScatterKernel

        self.init_nodedata = [-1 for _ in range(self.addresslayout.num_pe*self.addresslayout.num_nodes_per_pe)]

        self.init_messages = [list() for _ in range(self.addresslayout.num_pe)]
        for node in self.adj_dict:
            pe = node >> log2_int(self.addresslayout.num_nodes_per_pe)
            self.init_messages[pe].append(({'dest_id':node, 'sender':0, 'payload':node}))


        logger.info("Algorithm: CC")
        logger.info("Using HMC: " + ("YES" if self.use_hmc else "NO"))
        logger.info("nodeidsize = {}".format(self.addresslayout.nodeidsize))
        logger.info("edgeidsize = {}".format(self.addresslayout.edgeidsize))
        logger.info("peidsize = {}".format(self.addresslayout.peidsize))
        logger.info("num_pe = " + str(self.addresslayout.num_pe))
        logger.info("num_nodes_per_pe = " + str(self.addresslayout.num_nodes_per_pe))
        logger.info("max_edges_per_pe = " + str(self.addresslayout.max_edges_per_pe))
        logger.info("inter_pe_delay =" + str(self.addresslayout.inter_pe_delay))
