from migen import *
from migen.genlib.record import *

from tri.interfaces import payload_layout, edge_storage_layout

import logging

class ScatterKernel(Module):
    def __init__(self, config):

        self.update_in = Record(set_layout_parameters(payload_layout, **config.addresslayout.get_params()))
        self.num_neighbors_in = Signal(config.addresslayout.edgeidsize)
        self.neighbor_in = Signal(config.addresslayout.nodeidsize)
        self.edgedata_in = Record(set_layout_parameters(edge_storage_layout, **config.addresslayout.get_params()))
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

        dest_island = Signal()
        send_home = Signal()
        smaller = Signal()
        break_tie = Signal()
        pass_filter = Signal()

        self.comb += [
            self.ready.eq(self.message_ack),
            self.message_out.origin.eq(self.update_in.origin),
            self.message_out.hops.eq(self.update_in.hops),
            self.neighbor_out.eq(self.neighbor_in),
            self.sender_out.eq(self.sender_in),
            self.round_out.eq(self.round_in),
            self.barrier_out.eq(self.barrier_in),
            dest_island.eq(self.edgedata_in.degree < 2),
            smaller.eq(self.num_neighbors_in < self.edgedata_in.degree),
            break_tie.eq((self.num_neighbors_in == self.edgedata_in.degree) & (self.sender_in > self.neighbor_in)),
            send_home.eq(self.neighbor_in == self.update_in.origin),
            pass_filter.eq(~dest_island & ~smaller & ~break_tie & ~send_home),
            If(self.update_in.hops < 2,
                self.valid_out.eq(self.valid_in & pass_filter)
            ).Else(
                self.valid_out.eq(self.valid_in & send_home)
            )
        ]

    def gen_selfcheck(self, tb):
        logger = logging.getLogger("simulation.scatterkernel")
        num_pe = tb.config.addresslayout.num_pe
        pe_id = [s.scatterkernel for core in tb.cores for s in core.scatter].index(self)
        level = 0
        num_cycles = 0
        num_neighbors_in = 0
        num_messages_out = 0
        while not (yield tb.global_inactive):
            num_cycles += 1
            if (yield self.valid_out) and (yield self.message_ack) and (yield self.barrier_out):
                level += 1
                logger.info("{}: PE {} raised to level {}".format(num_cycles, pe_id, level))
            if (yield self.valid_in) and (yield self.ready):
                num_neighbors_in += 1
            if (yield self.valid_out) and (yield self.message_ack) and not (yield self.barrier_out):
                logger.debug("{}: PE {} message out (dest={} sender={} origin={} hops={})".format(num_cycles, pe_id, (yield self.neighbor_out), (yield self.sender_out), (yield self.message_out.origin), (yield self.message_out.hops)))
                num_messages_out += 1
            yield
