from migen import *
from migen.genlib.record import *

from pr_ex.interfaces import payload_layout
from fidiv import FloatIntDivider


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

        self.submodules.divider = FloatIntDivider()

        self.comb += [
            self.divider.dividend_i.eq(self.update_in.weight),
            self.divider.divisor_i.eq(self.num_neighbors_in),
            self.divider.valid_i.eq(self.valid_in),
            self.message_out.weight.eq(self.divider.quotient_o),
            self.valid_out.eq(self.divider.valid_o),
            self.divider.ce.eq(self.message_ack),
            self.ready.eq(self.message_ack)
        ]

        neighbor = [ Signal(config.addresslayout.nodeidsize) for _ in range(self.divider.latency + 1) ]
        sender = [ Signal(config.addresslayout.nodeidsize) for _ in range(self.divider.latency + 1) ]
        barrier = [ Signal() for _ in range(self.divider.latency + 1) ]
        roundpar = [ Signal(config.addresslayout.channel_bits) for _ in range(self.divider.latency + 1) ]

        self.sync += If(self.message_ack,
            [ neighbor[i+1].eq(neighbor[i]) for i in range(self.divider.latency) ],
            [ sender[i+1].eq(sender[i]) for i in range(self.divider.latency) ],
            [ barrier[i+1].eq(barrier[i]) for i in range(self.divider.latency) ],
            [ roundpar[i+1].eq(roundpar[i]) for i in range(self.divider.latency) ]
        )

        self.comb += [
            neighbor[0].eq(self.neighbor_in),
            sender[0].eq(self.sender_in),
            barrier[0].eq(self.barrier_in),
            roundpar[0].eq(self.round_in),
            self.neighbor_out.eq(neighbor[-1]),
            self.sender_out.eq(sender[-1]),
            self.barrier_out.eq(barrier[-1]),
            self.round_out.eq(roundpar[-1])
        ]
