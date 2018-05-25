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

        self.init_nodedata = [[convert_record_to_int(self.addresslayout.node_storage_layout, nneighbors=(len(self.adj_dict[self.addresslayout.global_adr(pe_adr=pe, local_adr=node)]) if self.addresslayout.global_adr(pe_adr=pe, local_adr=node) in self.adj_dict else 0), sum=0, nrecvd=0, active=0)  for node in range(max_node[pe] + 1)] for pe in range(self.addresslayout.num_pe)]

        self.has_edgedata = False

        init_messages = [list() for _ in range(self.addresslayout.num_pe)]
        for node in self.adj_dict:
            init_messages[self.addresslayout.pe_adr(node)].append(({'dest_id':node, 'sender':0, 'payload':self.addresslayout.const_base}))

        self.init_messages = init_messages
