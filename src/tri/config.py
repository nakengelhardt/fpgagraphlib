from migen import *
from tbsupport import *

from core_address import AddressLayout
from tri.interfaces import *
from tri.gatherapplykernel import GatherApplyKernel
from tri.scatterkernel import ScatterKernel

import logging

class Config:
    def __init__(self, adj_dict, **kwargs):
        self.name = "tri"
        logger = logging.getLogger('config')

        payloadsize = layout_len(set_layout_parameters(payload_layout, **kwargs))

        self.addresslayout = AddressLayout(payloadsize=payloadsize, **kwargs)
        self.addresslayout.node_storage_layout = set_layout_parameters(node_storage_layout, **self.addresslayout.get_params())

        self.adj_dict = adj_dict

        self.has_edgedata = True
        self.addresslayout.edgedatasize = layout_len(set_layout_parameters(edge_storage_layout, **kwargs))

        self.gatherapplykernel = GatherApplyKernel
        self.scatterkernel = ScatterKernel

        self.init_nodedata = [[] for _ in range(self.addresslayout.num_pe)]
        current_round = 0
        current_round_edges = 0

        max_node = self.addresslayout.max_node_per_pe(adj_dict)
        for node in range(max(max_node) + 1):
            for pe in range(self.addresslayout.num_pe):
                if node <= max_node[pe]:
                    nodeid = self.addresslayout.global_adr(pe_adr=pe, local_adr=node)
                    active = (1 if nodeid in self.adj_dict else 0)

                    self.init_nodedata[pe].append(convert_record_to_int(self.addresslayout.node_storage_layout,
                        send_in_level = current_round,
                        num_triangles = 0,
                        active = active
                    ))

                    if active:
                        num_neighbors = len(adj_dict[nodeid])
                        current_round_edges += num_neighbors
                        if current_round_edges > 1024:
                            current_round_edges = 0
                            current_round += 1




        adj_idx, adj_val = self.addresslayout.generate_partition(adj_dict)
        self.init_edgedata = [[len(adj_dict[j]) for j in adj_val[i]] for i in range(self.addresslayout.num_pe)]
