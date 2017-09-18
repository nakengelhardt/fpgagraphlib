from migen import *

from core_address import AddressLayout
from bfs.interfaces import node_storage_layout
from bfs.gatherkernel import GatherKernel
from bfs.applykernel import ApplyKernel
from bfs.scatterkernel import ScatterKernel

import logging

class Config:
    def __init__(self, adj_dict, use_hmc=False, share_mem_port=False, **kwargs):
        self.name = "bfs"
        logger = logging.getLogger('config')

        payloadsize = 1

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

        self.gatherkernel = GatherKernel
        self.applykernel = ApplyKernel
        self.scatterkernel = ScatterKernel

        self.init_nodedata = None

        init_root = 0
        while not init_root in adj_dict:
            init_root += 1

        self.init_messages = [list() for _ in range(self.addresslayout.num_pe)]
        self.init_messages[0].append({'dest_id':init_root, 'sender':init_root, 'payload':0})
