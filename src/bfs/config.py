from migen import *
from tbsupport import *
from core_config import *

from bfs.interfaces import *
# from bfs.gatherapplykernel import GatherApplyKernel
from bfs.gatherkernel import GatherKernel
from bfs.applykernel import ApplyKernel
from bfs.scatterkernel import ScatterKernel

class Config(CoreConfig):
    def __init__(self, graph, **kwargs):
        logger = logging.getLogger("config.bfs")

        self.name = "bfs"

        # self.gatherapplykernel = GatherApplyKernel
        self.gatherkernel = GatherKernel
        self.applykernel = ApplyKernel
        self.scatterkernel = ScatterKernel

        first_node = True
        for node in graph:
            if first_node:
                graph.nodes[node]['parent'] = 1
            else:
                graph.nodes[node]['parent'] = 0
            graph.nodes[node]['active'] = 1 if first_node else 0
            first_node = False

        super().__init__(graph, node_storage_layout, update_layout, message_layout, **kwargs)

        for node in self.graph:
            if self.graph.nodes[node]['active']:
                logger.info("Initial node: {}".format(node))
