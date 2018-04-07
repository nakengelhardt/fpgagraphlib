from migen import *
from tbsupport import *

from core_address import AddressLayout
from sssp.interfaces import node_storage_layout
from sssp.gatherkernel import GatherKernel
from sssp.applykernel import ApplyKernel
from sssp.scatterkernel import ScatterKernel

import random
import logging

class Config:
    def __init__(self, adj_dict, **kwargs):
        self.name = "sssp"

        logger = logging.getLogger('config')

        payloadsize = 8

        self.addresslayout = AddressLayout(payloadsize=payloadsize, **kwargs)
        self.addresslayout.edgedatasize = payloadsize
        self.addresslayout.node_storage_layout = set_layout_parameters(node_storage_layout, **self.addresslayout.get_params())

        self.adj_dict = adj_dict

        self.gatherkernel = GatherKernel
        self.applykernel = ApplyKernel
        self.scatterkernel = ScatterKernel

        max_node = self.addresslayout.max_per_pe(adj_dict)
        self.init_nodedata = [[convert_record_to_int(self.addresslayout.node_storage_layout, dist=ones(self.addresslayout.nodeidsize), parent=0, active=0) for node in range(max_node[pe] + 1)] for pe in range(self.addresslayout.num_pe)]

        self.has_edgedata = True

        self.init_edgedata = [[random.randrange(1,10) for _ in range(self.addresslayout.max_edges_per_pe)] for _ in range(self.addresslayout.num_pe)]

        init_root = 0
        while not init_root in adj_dict:
            init_root += 1

        self.init_messages = [list() for _ in range(self.addresslayout.num_pe)]
        self.init_messages[self.addresslayout.pe_adr(init_root)].append({'dest_id':init_root, 'sender':init_root, 'payload':0})
