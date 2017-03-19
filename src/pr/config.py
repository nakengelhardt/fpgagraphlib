from migen import *
from migen.genlib.record import *

from tbsupport import convert_float_to_32b_int, convert_32b_int_to_float, convert_int_to_record

from core_address import AddressLayout
from pr.interfaces import payload_layout, node_storage_layout
from pr.applykernel import ApplyKernel
from pr.scatterkernel import ScatterKernel

import logging

class Config:
    def __init__(self, adj_dict, use_hmc=False, share_mem_port=False, **kwargs):
        self.name = "pr"

        logger = logging.getLogger('config')

        floatsize = 32
        payloadsize = layout_len(set_layout_parameters(payload_layout, floatsize=floatsize))

        self.use_hmc = use_hmc
        self.share_mem_port = share_mem_port

        self.addresslayout = AddressLayout(payloadsize=payloadsize, **kwargs)
        self.addresslayout.floatsize = floatsize

        self.addresslayout.node_storage_layout_len = layout_len(set_layout_parameters(node_storage_layout, **self.addresslayout.get_params()))

        num_nodes = len(adj_dict)
        self.addresslayout.const_base = convert_float_to_32b_int(0.15/num_nodes)

        self.applykernel = ApplyKernel
        self.scatterkernel = ScatterKernel

        self.adj_dict = adj_dict
        if self.use_hmc:
            adj_idx, adj_val = self.addresslayout.generate_partition_flat(self.adj_dict)
        else:
            adj_idx, adj_val = self.addresslayout.generate_partition(self.adj_dict)
        self.adj_idx = adj_idx
        self.adj_val = adj_val

        max_node = self.addresslayout.max_per_pe(adj_dict)
        self.init_nodedata = [[len(self.adj_dict[self.addresslayout.global_adr(pe_adr=pe, local_adr=node)]) if self.addresslayout.global_adr(pe_adr=pe, local_adr=node) in self.adj_dict else 0 for node in range(max_node[pe] + 1)] for pe in range(self.addresslayout.num_pe)]
        print("Nodes per PE: {}".format([(pe, len(self.init_nodedata[pe])) for pe in range(self.addresslayout.num_pe)]))

        self.has_edgedata = False

        init_messages = [list() for _ in range(self.addresslayout.num_pe)]
        for node in self.adj_dict:
            pe = node >> log2_int(self.addresslayout.num_nodes_per_pe)
            init_messages[pe].append(({'dest_id':node, 'sender':0, 'payload':self.addresslayout.const_base}))

        self.init_messages = init_messages
