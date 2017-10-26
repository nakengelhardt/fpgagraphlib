from migen import *
from migen.genlib.record import *

from cc.interfaces import payload_layout


class ScatterKernel(Module):
    def __init__(self, config):

        self.update_in = Record(set_layout_parameters(payload_layout, **config.addresslayout.get_params()))
        self.num_neighbors_in = Signal(config.addresslayout.edgeidsize)
        self.neighbor_in = Signal(config.addresslayout.nodeidsize)
        self.sender_in = Signal(config.addresslayout.nodeidsize)
        self.round_in = Signal(config.addresslayout.channel_bits)
        self.barrier_in = Signal()
        self.valid_in = Signal()
        self.ready = Signal()

        self.message_out = Record(set_layout_parameters(payload_layout, **config.addresslayout.get_params()))
        self.neighbor_out = Signal(config.addresslayout.nodeidsize)
        self.sender_out = Signal(config.addresslayout.nodeidsize)
        self.round_out = Signal(config.addresslayout.channel_bits)
        self.valid_out = Signal()
        self.message_ack = Signal()
        self.barrier_out = Signal()

        ####

        self.comb += [
            self.message_out.eq(self.update_in),
            self.neighbor_out.eq(self.neighbor_in),
            self.sender_out.eq(self.sender_in),
            self.round_out.eq(self.round_in),
            self.valid_out.eq(self.valid_in),
            self.barrier_out.eq(self.barrier_in),
            self.ready.eq(self.message_ack)
        ]
