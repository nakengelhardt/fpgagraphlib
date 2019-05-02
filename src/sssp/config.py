from migen import *
from tbsupport import *
from core_config import *

from sssp.interfaces import *
from sssp.gatherkernel import GatherKernel
from sssp.applykernel import ApplyKernel
from sssp.scatterkernel import ScatterKernel

import random

class Config(CoreConfig):
    def __init__(self, graph, **kwargs):
        self.name = "sssp"

        self.gatherkernel = GatherKernel
        self.applykernel = ApplyKernel
        self.scatterkernel = ScatterKernel

        edgedatasize = 4

        first_node = True
        for node in graph:
            graph.nodes[node]['parent'] = 0
            if first_node:
                graph.nodes[node]['dist'] = 0
                graph.nodes[node]['active'] = 1
            else:
                graph.nodes[node]['dist'] = 2**edgedatasize - 1
                graph.nodes[node]['active'] = 0
            first_node = False

        for u,v in graph.edges():
            graph.get_edge_data(u, v)['dist'] = random.randrange(1,15)
            graph.get_edge_data(v, u)['dist'] = graph.get_edge_data(u, v)['dist']

        super().__init__(graph, node_storage_layout, update_layout, message_layout,
            has_edgedata = True, # Does this algorithm associate data with edges? (Defaults to false.)
            edge_storage_layout = edge_storage_layout, # Mandatory if has_edgedata is True.
            edgedatasize = edgedatasize,
            **kwargs)
