from migen import *
from tbsupport import *

from core_address import AddressLayout
from tri.interfaces import *
from tri.gatherapplykernel import GatherApplyKernel
from tri.scatterkernel import ScatterKernel
from tri.preprocess import count_triangles

import logging

class Config:
    def __init__(self, adj_dict, **kwargs):
        self.name = "tri"
        logger = logging.getLogger('config')

        payloadsize = layout_len(set_layout_parameters(payload_layout, **kwargs))

        self.addresslayout = AddressLayout(payloadsize=payloadsize, **kwargs)
        self.addresslayout.node_storage_layout = set_layout_parameters(node_storage_layout, **self.addresslayout.get_params())

        self.adj_dict = adj_dict
        # logger.info("Graph has {} triangles".format(count_triangles(adj_dict)))

        self.has_edgedata = True
        self.addresslayout.edgedatasize = layout_len(set_layout_parameters(edge_storage_layout, **kwargs))

        self.gatherapplykernel = GatherApplyKernel
        self.scatterkernel = ScatterKernel

        self.init_nodedata = [[] for _ in range(self.addresslayout.num_pe)]


        def edge_dir(i,j, adj_dict):
            if j not in adj_dict[i]:
                return False
            if len(adj_dict[j]) < 2:
                return False
            if len(adj_dict[i]) < len(adj_dict[j]):
                return False
            if len(adj_dict[i]) == len(adj_dict[j]) and i >= j:
                return False
            return True

        def num_active_edges(i, adj_dict):
            num_edges = 0
            for j in adj_dict[i]:
                if edge_dir(i, j, adj_dict):
                    num_edges += 1
            return num_edges

        def sum_active_edges(k, adj_dict):
            num_edges = 0
            for i in adj_dict[k]:
                if edge_dir(k, i, adj_dict):
                    num_edges += num_active_edges(i, adj_dict)
            return num_edges

        current_round = 0
        current_round_edges = 0
        max_round_edges = 0
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
                        # active_edges = len(adj_dict[nodeid])
                        active_edges = sum_active_edges(nodeid, self.adj_dict)
                        current_round_edges += active_edges
                        if current_round_edges > (1<<10):
                            current_round_edges = 0
                            current_round += 1
                        if max_round_edges < active_edges:
                            max_round_edges = active_edges
        print(max_round_edges)


        logger.info("Activation spread over {} supersteps.".format(current_round+1))



        adj_idx, adj_val = self.addresslayout.generate_partition(adj_dict)
        self.init_edgedata = [[len(adj_dict[j]) for j in adj_val[i]] for i in range(self.addresslayout.num_pe)]
