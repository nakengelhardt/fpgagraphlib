from migen import *
from tbsupport import *

from core_address import AddressLayout
from cc.interfaces import node_storage_layout
from cc.gatherkernel import GatherKernel
from cc.applykernel import ApplyKernel
from cc.scatterkernel import ScatterKernel

import logging

class Config:
    def __init__(self, adj_dict, **kwargs):
        self.name = "cc"
        logger = logging.getLogger('config')

        payloadsize = kwargs['nodeidsize']

        self.addresslayout = AddressLayout(payloadsize=payloadsize, **kwargs)
        self.addresslayout.node_storage_layout = set_layout_parameters(node_storage_layout, **self.addresslayout.get_params())

        self.adj_dict = adj_dict

        self.has_edgedata = False

        self.gatherkernel = GatherKernel
        self.applykernel = ApplyKernel
        self.scatterkernel = ScatterKernel

        max_node = self.addresslayout.max_node_per_pe(adj_dict)
        self.init_nodedata = [[convert_record_to_int(self.addresslayout.node_storage_layout, color=self.addresslayout.global_adr(pe, node), active=(1 if self.addresslayout.global_adr(pe, node) in adj_dict else 0)) for node in range(max_node[pe] + 1)] for pe in range(self.addresslayout.num_pe)]
