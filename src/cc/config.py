from migen import *
from tbsupport import *

from core_address import AddressLayout
from cc.interfaces import node_storage_layout
from cc.gatherkernel import GatherKernel
from cc.applykernel import ApplyKernel
from cc.scatterkernel import ScatterKernel

import logging

class Config:
    def __init__(self, adj_dict, use_hmc=False, share_mem_port=False, **kwargs):
        self.name = "cc"
        logger = logging.getLogger('config')

        payloadsize = kwargs['nodeidsize']

        self.addresslayout = AddressLayout(payloadsize=payloadsize, **kwargs)
        self.addresslayout.node_storage_layout = set_layout_parameters(node_storage_layout, **self.addresslayout.get_params())

        self.use_hmc = use_hmc
        self.share_mem_port = share_mem_port

        self.adj_dict = adj_dict
        if self.use_hmc:
            adj_idx, adj_val = self.addresslayout.generate_partition_flat(self.adj_dict)
        else:
            adj_idx, adj_val = self.addresslayout.generate_partition(self.adj_dict)
        self.adj_idx = adj_idx
        self.adj_val = adj_val

        self.has_edgedata = False
        self.use_hmc = use_hmc

        self.gatherkernel = GatherKernel
        self.applykernel = ApplyKernel
        self.scatterkernel = ScatterKernel

        max_node = self.addresslayout.max_per_pe(adj_dict)
        self.init_nodedata = [[convert_record_to_int(self.addresslayout.node_storage_layout, color=ones(self.addresslayout.nodeidsize), active=0) for node in range(max_node[pe] + 1)] for pe in range(self.addresslayout.num_pe)]

        self.init_messages = [list() for _ in range(self.addresslayout.num_pe)]
        for node in self.adj_dict:
            self.init_messages[self.addresslayout.pe_adr(node)].append(({'dest_id':node, 'sender':0, 'payload':node}))
