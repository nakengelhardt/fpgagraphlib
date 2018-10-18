from migen import *
from tbsupport import *
from core_config import *

from tri.interfaces import *
from tri.gatherapplykernel import GatherApplyKernel
from tri.scatterkernel import ScatterKernel
from tri.preprocess import *

import logging

class Config(CoreConfig):
    def __init__(self, graph, **kwargs):
        self.name = "tri"
        logger = logging.getLogger('config')

        self.gatherapplykernel = GatherApplyKernel
        self.scatterkernel = ScatterKernel

        for u,v in graph.edges():
            graph.get_edge_data(u, v)['degree'] = len(graph[u])

        super().__init__(graph, node_storage_layout, update_layout, message_layout,
            has_edgedata = True,
            edge_storage_layout=edge_storage_layout,
            **kwargs)

        logger.info("Graph has {} triangles".format(count_triangles(self.adj_dict)))

        current_round = 0
        current_round_edges = 0
        max_round_edges = 0
        max_node = self.addresslayout.max_node_per_pe(self.adj_dict)
        for node in range(max(max_node) + 1):
            for pe in range(self.addresslayout.num_pe):
                nodeid = self.addresslayout.global_adr(pe_adr=pe, local_adr=node)
                if node <= max_node[pe] and nodeid in self.adj_dict:
                    self.init_nodedata[pe][node] = convert_record_to_int(self.addresslayout.node_storage_layout,
                        send_in_level = current_round,
                        num_triangles = 0,
                        active = 1
                    )

                    # active_edges = len(self.adj_dict[nodeid])
                    active_edges = sum_active_edges(nodeid, self.adj_dict)
                    current_round_edges += active_edges
                    if current_round_edges > (1<<10):
                        current_round_edges = 0
                        current_round += 1
                    if max_round_edges < active_edges:
                        max_round_edges = active_edges

        logger.info("Activation spread over {} supersteps.".format(current_round+1))
