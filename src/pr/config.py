from migen import *
from migen.genlib.record import *

from tbsupport import *

from core_address import AddressLayout
from pr.interfaces import payload_layout, node_storage_layout
from pr.gatherkernel import GatherKernel
from pr.applykernel import ApplyKernel
from pr.scatterkernel import ScatterKernel

import logging

class Config:
    def __init__(self, adj_dict, **kwargs):
        self.name = "pr"
        self.total_pr_rounds = 30

        logger = logging.getLogger('config')
        logger.info("total_pr_rounds = {}".format(self.total_pr_rounds))

        floatsize = 32
        payloadsize = layout_len(set_layout_parameters(payload_layout, floatsize=floatsize))

        self.addresslayout = AddressLayout(payloadsize=payloadsize, **kwargs)
        self.addresslayout.floatsize = floatsize

        self.addresslayout.node_storage_layout = set_layout_parameters(node_storage_layout, **self.addresslayout.get_params())

        num_nodes = len(adj_dict)
        self.addresslayout.const_base = convert_float_to_32b_int(0.15/num_nodes)

        self.gatherkernel = GatherKernel
        self.applykernel = ApplyKernel
        self.scatterkernel = ScatterKernel

        self.adj_dict = adj_dict

        max_node = self.addresslayout.max_node_per_pe(adj_dict)

        self.init_nodedata = [[0  for node in range(max_node[pe] + 1)] for pe in range(self.addresslayout.num_pe)]
        for node in adj_dict:
            pe_adr = self.addresslayout.pe_adr(node)
            local_adr  = self.addresslayout.local_adr(node)
            nneighbors=len(self.adj_dict[node])
            self.init_nodedata[pe_adr][local_adr] = convert_record_to_int(self.addresslayout.node_storage_layout, nneighbors=nneighbors, nrecvd=nneighbors, sum=self.addresslayout.const_base, active=1)

        self.has_edgedata = False
