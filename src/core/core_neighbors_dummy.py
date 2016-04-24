from migen import *

class Neighbors(Module):
    def __init__(self, config, adj_val, edge_data=None):
        nodeidsize = config.addresslayout.nodeidsize
        num_nodes_per_pe = config.addresslayout.num_nodes_per_pe
        num_pe = config.addresslayout.num_pe
        edgeidsize = config.addresslayout.edgeidsize
        max_edges_per_pe = config.addresslayout.max_edges_per_pe

        # input
        self.start_idx = Signal(edgeidsize)
        self.num_neighbors = Signal(edgeidsize)
        self.valid = Signal()
        self.ack = Signal()
        self.barrier_in = Signal()
        self.message_in = Signal(config.addresslayout.payloadsize)
        self.sender_in = Signal(config.addresslayout.nodeidsize)
        self.round_in = Signal()

        # output
        self.neighbor = Signal(nodeidsize)
        self.neighbor_valid = Signal()
        self.neighbor_ack = Signal()
        self.barrier_out = Signal()
        self.message_out = Signal(config.addresslayout.payloadsize)
        self.sender_out = Signal(config.addresslayout.nodeidsize)
        self.round_out = Signal()
        self.num_neighbors_out = Signal(edgeidsize)