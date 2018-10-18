from migen import *
from tbsupport import *
from core_config import *

from cc.interfaces import *
from cc.gatherkernel import GatherKernel
from cc.applykernel import ApplyKernel
from cc.scatterkernel import ScatterKernel

import logging

class Config(CoreConfig):
    def __init__(self, graph, **kwargs):
        self.name = "cc"

        self.gatherkernel = GatherKernel
        self.applykernel = ApplyKernel
        self.scatterkernel = ScatterKernel

        for node in graph:
            graph.node[node]['color'] = node
            graph.node[node]['active'] = 1

        super().__init__(graph, node_storage_layout, update_layout, message_layout, **kwargs)
