from migen import *
from migen.genlib.record import *

from bfs.interfaces import payload_layout
from fidiv import FloatIntDivider


class ScatterKernel(Module):
    def __init__(self, addresslayout):

        self.message_in = Record(set_layout_parameters(payload_layout, **addresslayout.get_params()))
        self.num_neighbors_in = Signal(addresslayout.edgeidsize)
        self.neighbor_in = Signal(addresslayout.nodeidsize)
        self.sender_in = Signal(addresslayout.nodeidsize)
        self.round_in = Signal()
        self.barrier_in = Signal()
        self.valid_in = Signal()
        self.ready = Signal()

        self.message_out = Record(set_layout_parameters(payload_layout, **addresslayout.get_params()))
        self.neighbor_out = Signal(addresslayout.nodeidsize)
        self.sender_out = Signal(addresslayout.nodeidsize)
        self.round_out = Signal()
        self.valid_out = Signal()
        self.message_ack = Signal()
        self.barrier_out = Signal()

        ####

        self.comb += [
            self.neighbor_out.eq(self.neighbor_in),
            self.sender_out.eq(self.sender_in),
            self.round_out.eq(self.round_in),
            self.valid_out.eq(self.valid_in),
            self.barrier_out.eq(self.barrier_in),
            self.ready.eq(self.message_ack)
        ]