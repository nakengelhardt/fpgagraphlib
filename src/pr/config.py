from migen import *
from migen.genlib.record import *

from tbsupport import convert_float_to_32b_int, convert_32b_int_to_float, convert_int_to_record

from core_address import AddressLayout
from pr.interfaces import payload_layout, node_storage_layout
from pr.applykernel import ApplyKernel
from pr.scatterkernel import ScatterKernel

import logging

class Config:
    def __init__(self, adj_dict):
        self.name = "pr"

        logger = logging.getLogger('config')

        # nodeidsize = 32
        # num_nodes_per_pe = 2**11
        # edgeidsize = 32
        # max_edges_per_pe = 2**13
        # num_pe = 9
        # peidsize = bits_for(num_pe)

        # nodeidsize = 16
        # num_nodes_per_pe = 2**10
        # edgeidsize = 16
        # max_edges_per_pe = 2**14
        # num_pe = 32
        # peidsize = log2_int(num_pe)

        # nodeidsize = 16
        # num_nodes_per_pe = 2**8
        # edgeidsize = 16
        # max_edges_per_pe = 2**12
        # num_pe = 8
        # peidsize = log2_int(num_pe)

        nodeidsize = 32
        num_nodes_per_pe = 2**4
        edgeidsize = 32
        max_edges_per_pe = 2**6
        peidsize = 4
        num_pe = 16

        pe_groups = 1
        inter_pe_delay = 0

        assert(num_pe * num_nodes_per_pe > len(adj_dict))

        floatsize = 32
        payloadsize = layout_len(set_layout_parameters(payload_layout, floatsize=floatsize))

        self.addresslayout = AddressLayout(nodeidsize=nodeidsize, edgeidsize=edgeidsize, peidsize=peidsize, num_pe=num_pe, num_nodes_per_pe=num_nodes_per_pe, max_edges_per_pe=max_edges_per_pe, payloadsize=payloadsize)
        self.addresslayout.floatsize = floatsize
        self.addresslayout.pe_groups = pe_groups
        self.addresslayout.inter_pe_delay = inter_pe_delay

        self.addresslayout.node_storage_layout_len = layout_len(set_layout_parameters(node_storage_layout, **self.addresslayout.get_params()))

        num_nodes = len(adj_dict)
        self.addresslayout.const_base = convert_float_to_32b_int(0.15/num_nodes)

        self.applykernel = ApplyKernel
        self.scatterkernel = ScatterKernel

        self.use_hmc = False

        self.adj_dict = adj_dict
        if self.use_hmc:
            adj_idx, adj_val = self.addresslayout.generate_partition_flat(self.adj_dict)
        else:
            adj_idx, adj_val = self.addresslayout.generate_partition(self.adj_dict)
        self.adj_idx = adj_idx
        self.adj_val = adj_val

        self.init_nodedata = [0] + [len(self.adj_dict[node]) for node in range(1, num_nodes+1)] + [0 for _ in range(num_nodes+1, num_pe*num_nodes_per_pe)]

        self.has_edgedata = False

        init_messages = [list() for _ in range(num_pe)]
        for node in self.adj_dict:
            pe = node >> log2_int(num_nodes_per_pe)
            init_messages[pe].append(({'dest_id':node, 'sender':0, 'payload':self.addresslayout.const_base}))

        self.init_messages = init_messages

        logger.info("Algorithm: PageRank")
        logger.info("Using HMC: " + "YES" if self.use_hmc else "NO")
        logger.info("nodeidsize = {}".format(nodeidsize))
        logger.info("edgeidsize = {}".format(edgeidsize))
        logger.info("peidsize = {}".format(peidsize))
        logger.info("num_pe = " + str(num_pe))
        logger.info("num_nodes_per_pe = " + str(num_nodes_per_pe))
        logger.info("max_edges_per_pe = " + str(max_edges_per_pe))
        logger.info("inter_pe_delay =" + str(inter_pe_delay))
