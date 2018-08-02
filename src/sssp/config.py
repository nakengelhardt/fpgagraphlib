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
    def __init__(self, adj_dict, use_hmc=False, share_mem_port=False, **kwargs):
        self.name = "sssp"

        logger = logging.getLogger('config')

        payloadsize = kwargs['nodeidsize']

        self.addresslayout = AddressLayout(payloadsize=payloadsize, **kwargs)
        self.addresslayout.edgedatasize = 8
        self.addresslayout.node_storage_layout = set_layout_parameters(node_storage_layout, **self.addresslayout.get_params())

        #edgedata not supported yet on HMC
        assert(use_hmc==False)
        self.use_hmc = use_hmc
        self.share_mem_port = share_mem_port

        self.adj_dict = adj_dict
        if self.use_hmc:
            adj_idx, adj_val = self.addresslayout.generate_partition_flat(self.adj_dict)
        else:
            adj_idx, adj_val = self.addresslayout.generate_partition(self.adj_dict)
        self.adj_idx = adj_idx
        self.adj_val = adj_val

        self.gatherkernel = GatherKernel
        self.applykernel = ApplyKernel
        self.scatterkernel = ScatterKernel

        max_node = self.addresslayout.max_node_per_pe(adj_dict)
        self.init_nodedata = [[convert_record_to_int(self.addresslayout.node_storage_layout, dist=2**self.addresslayout.edgedatasize - 1, parent=0, active=0) for node in range(max_node[pe] + 1)] for pe in range(self.addresslayout.num_pe)]

        self.has_edgedata = True

        self.init_edgedata = [[random.randrange(1,10) for _ in range(len(adj_val[i]))] for i in range(self.addresslayout.num_pe)]

        init_root = 0
        while not init_root in adj_dict:
            init_root += 1

        self.init_messages = [list() for _ in range(self.addresslayout.num_pe)]
        self.init_messages[0].append({'dest_id':init_root, 'sender':init_root, 'payload':0})
