from migen import *
from migen.genlib.record import *

from tbsupport import *

from core_config import *
from pr.interfaces import *
from pr.gatherkernel import GatherKernel
from pr.applykernel import ApplyKernel
from pr.scatterkernel import ScatterKernel

import logging

class Config(CoreConfig):
    def __init__(self, graph, **kwargs):
        self.name = "pr"
        self.total_pr_rounds = 30

        logger = logging.getLogger('config')
        logger.info("total_pr_rounds = {}".format(self.total_pr_rounds))

        self.gatherkernel = GatherKernel
        self.applykernel = ApplyKernel
        self.scatterkernel = ScatterKernel

        floatsize = 32
        self.const_base = convert_float_to_32b_int(0.15/graph.number_of_nodes())

        for node in graph:
            graph.nodes[node]['nneighbors'] = len(graph[node])
            graph.nodes[node]['nrecvd'] = graph.nodes[node]['nneighbors']
            graph.nodes[node]['sum'] = convert_float_to_32b_int(0.85/graph.number_of_nodes())
            # the apply phase performs (1-d)/N + d * sum
            # initial PR in first round should be 1/N; therefore sum must be initialized to d/N
            graph.nodes[node]['active'] = 1

        super().__init__(graph, node_storage_layout, update_layout, message_layout,
            floatsize = 32,
            **kwargs)
