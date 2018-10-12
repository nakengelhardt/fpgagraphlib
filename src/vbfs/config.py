from migen import *
from tbsupport import *

from core_address import AddressLayout
from vbfs.interfaces import node_storage_layout

from core_netlistkernelwrapper import *

import logging

class Config:
    def __init__(self, adj_dict, **kwargs):
        self.name = "vbfs"
        logger = logging.getLogger('config')

        payloadsize = 1

        self.addresslayout = AddressLayout(payloadsize=payloadsize, **kwargs)
        self.addresslayout.node_storage_layout = set_layout_parameters(node_storage_layout, **self.addresslayout.get_params())

        self.adj_dict = adj_dict

        self.has_edgedata = False

        # self.gatherapplykernel = GatherApplyKernel
        self.gatherkernel = NetlistGatherKernelWrapper
        self.applykernel = NetlistApplyKernelWrapper
        self.scatterkernel = NetlistScatterKernelWrapper

        init_root = 0
        while not init_root in adj_dict:
            init_root += 1

        max_node = self.addresslayout.max_node_per_pe(adj_dict)
        self.init_nodedata = [[convert_record_to_int(self.addresslayout.node_storage_layout, parent=(init_root if self.addresslayout.global_adr(pe, node) == init_root else 0), active=(1 if self.addresslayout.global_adr(pe, node) == init_root else 0)) for node in range(max_node[pe] + 1)] for pe in range(self.addresslayout.num_pe)]
