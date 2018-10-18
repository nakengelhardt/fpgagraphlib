from migen import *
from tbsupport import *
from core_config import *

from vbfs.interfaces import *
from core_netlistkernelwrapper import *

import logging

class Config(CoreConfig):
    def __init__(self, graph, **kwargs):
        self.name = "vbfs"

        # self.gatherapplykernel = GatherApplyKernel
        self.gatherkernel = NetlistGatherKernelWrapper
        self.applykernel = NetlistApplyKernelWrapper
        self.scatterkernel = NetlistScatterKernelWrapper

        first_node = True
        for node in graph:
            if first_node:
                graph.nodes[node]['parent'] = 1
            else:
                graph.nodes[node]['parent'] = 0
            graph.nodes[node]['active'] = 1 if first_node else 0
            first_node = False

        super().__init__(graph, node_storage_layout, update_layout, message_layout, **kwargs)
