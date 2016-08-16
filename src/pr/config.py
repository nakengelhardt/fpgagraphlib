from migen import *
from migen.genlib.record import *

from tbsupport import convert_float_to_32b_int, convert_32b_int_to_float, convert_int_to_record

from core_address import AddressLayout
from pr.interfaces import payload_layout, node_storage_layout
from pr.applykernel import ApplyKernel
from pr.scatterkernel import ScatterKernel

import logging

class Config:
    def __init__(self, adj_dict, use_hmc=False, **kwargs):
        self.name = "pr"

        logger = logging.getLogger('config')

        floatsize = 32
        payloadsize = layout_len(set_layout_parameters(payload_layout, floatsize=floatsize))

        self.use_hmc = use_hmc

        self.addresslayout = AddressLayout(payloadsize=payloadsize, **kwargs)
        self.addresslayout.floatsize = floatsize

        self.addresslayout.node_storage_layout_len = layout_len(set_layout_parameters(node_storage_layout, **self.addresslayout.get_params()))

        num_nodes = len(adj_dict)
        self.addresslayout.const_base = convert_float_to_32b_int(0.15/num_nodes)

        self.applykernel = ApplyKernel
        self.scatterkernel = ScatterKernel

        self.adj_dict = adj_dict
        if self.use_hmc:
            adj_idx, adj_val = self.addresslayout.generate_partition_flat(self.adj_dict)
        else:
            adj_idx, adj_val = self.addresslayout.generate_partition(self.adj_dict)
        self.adj_idx = adj_idx
        self.adj_val = adj_val

        self.init_nodedata = [0] + [len(self.adj_dict[node]) for node in range(1, num_nodes+1)] + [0 for _ in range(num_nodes+1, self.addresslayout.num_pe*self.addresslayout.num_nodes_per_pe)]

        self.has_edgedata = False

        init_messages = [list() for _ in range(self.addresslayout.num_pe)]
        for node in self.adj_dict:
            pe = node >> log2_int(self.addresslayout.num_nodes_per_pe)
            init_messages[pe].append(({'dest_id':node, 'sender':0, 'payload':self.addresslayout.const_base}))

        self.init_messages = init_messages

        logger.info("Algorithm: PageRank")
        logger.info("Using HMC: " + "YES" if self.use_hmc else "NO")
        logger.info("nodeidsize = {}".format(self.addresslayout.nodeidsize))
        logger.info("edgeidsize = {}".format(self.addresslayout.edgeidsize))
        logger.info("peidsize = {}".format(self.addresslayout.peidsize))
        logger.info("num_pe = " + str(self.addresslayout.num_pe))
        logger.info("num_nodes_per_pe = " + str(self.addresslayout.num_nodes_per_pe))
        logger.info("max_edges_per_pe = " + str(self.addresslayout.max_edges_per_pe))
        logger.info("inter_pe_delay =" + str(self.addresslayout.inter_pe_delay))
