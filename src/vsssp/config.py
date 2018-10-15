from migen import *
from tbsupport import *

from core_address import AddressLayout
from vsssp.interfaces import node_storage_layout

from core_netlistkernelwrapper import *

import random
import logging

class Config:
    def __init__(self, adj_dict, **kwargs):
        self.name = "vsssp"
        logger = logging.getLogger('config')

        payloadsize = 8

        self.addresslayout = AddressLayout(payloadsize=payloadsize, **kwargs)
        self.addresslayout.edgedatasize = 8
        self.addresslayout.node_storage_layout = set_layout_parameters(node_storage_layout, **self.addresslayout.get_params())

        self.adj_dict = adj_dict

        self.gatherkernel = NetlistGatherKernelWrapper
        self.applykernel = NetlistApplyKernelWrapper
        self.scatterkernel = NetlistScatterKernelWrapper

        init_root = 0
        while not init_root in adj_dict:
            init_root += 1

        max_node = self.addresslayout.max_node_per_pe(adj_dict)
        self.init_nodedata = [[convert_record_to_int(self.addresslayout.node_storage_layout, dist=(0 if self.addresslayout.global_adr(pe, node)==init_root else 2**self.addresslayout.edgedatasize - 1), parent=0, active=(1 if self.addresslayout.global_adr(pe, node)==init_root else 0)) for node in range(max_node[pe] + 1)] for pe in range(self.addresslayout.num_pe)]

        self.has_edgedata = True

        adj_idx, adj_val = self.addresslayout.generate_partition(adj_dict)
        self.init_edgedata = [[random.randrange(1,10) for _ in range(len(adj_val[i]))] for i in range(self.addresslayout.num_pe)]
