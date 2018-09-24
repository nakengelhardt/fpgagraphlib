from migen import *
from migen.genlib.record import *

from tri.interfaces import payload_layout, node_storage_layout

import logging

class GatherApplyKernel(Module):
    def __init__(self, config):
        nodeidsize = config.addresslayout.nodeidsize

        self.level_in = Signal(32)
        self.nodeid_in = Signal(nodeidsize)
        self.sender_in = Signal(nodeidsize)
        self.message_in = Record(set_layout_parameters(payload_layout, **config.addresslayout.get_params()))
        self.message_in_valid = Signal()
        self.state_in = Record(set_layout_parameters(node_storage_layout, **config.addresslayout.get_params()))
        self.state_in_valid = Signal()
        self.round_in = Signal(config.addresslayout.channel_bits)
        self.barrier_in = Signal()
        self.valid_in = Signal()
        self.ready = Signal()

        self.nodeid_out = Signal(nodeidsize)
        self.state_out = Record(set_layout_parameters(node_storage_layout, **config.addresslayout.get_params()))
        self.state_barrier = Signal()
        self.state_valid = Signal()
        self.state_ack = Signal()

        self.update_out = Record(set_layout_parameters(payload_layout, **config.addresslayout.get_params()))
        self.update_sender = Signal(nodeidsize)
        self.update_round = Signal(config.addresslayout.channel_bits)
        self.barrier_out = Signal()
        self.update_valid = Signal()
        self.update_ack = Signal()

        self.kernel_error = Signal()

        self.comb += [
            self.ready.eq(self.update_ack & self.state_ack),
            self.nodeid_out.eq(self.nodeid_in),
            self.state_out.send_in_level.eq(self.state_in.send_in_level),
            self.state_barrier.eq(self.barrier_in),
            self.state_valid.eq(self.valid_in & self.state_in_valid & self.update_ack),
            self.update_sender.eq(self.nodeid_in),
            self.update_round.eq(self.round_in),
            self.barrier_out.eq(self.barrier_in),

            If(self.message_in_valid,
                If((self.message_in.hops == 2),
                    self.state_out.num_triangles.eq(self.state_in.num_triangles + 1)
                ).Else(
                    self.state_out.num_triangles.eq(self.state_in.num_triangles)
                ),
                self.state_out.active.eq(self.state_in.active),

                self.update_out.origin.eq(self.message_in.origin),
                self.update_out.hops.eq(self.message_in.hops + 1),

                self.update_valid.eq(self.valid_in & (self.message_in.hops < 2) & self.state_ack)
            ).Else(
                self.state_out.num_triangles.eq(self.state_in.num_triangles),
                self.state_out.active.eq(self.state_in.active & ~self.update_valid),
                self.update_out.origin.eq(self.nodeid_in),
                self.update_out.hops.eq(0),

                self.update_valid.eq(self.valid_in & self.state_ack & ((self.state_in_valid & self.state_in.active & (self.level_in == self.state_in.send_in_level)) | self.barrier_in))
            )
        ]

        self.num_triangles = Signal(32)
        self.sync += If(self.valid_in & self.ready,
            If(self.message_in_valid & (self.message_in.hops == 2),
                self.num_triangles.eq(self.num_triangles + 1),
            )
        )

    def gen_selfcheck(self, tb):
        logger = logging.getLogger("simulation.applykernel")
        num_pe = tb.config.addresslayout.num_pe
        pe_id = [a.gatherapplykernel for core in tb.cores for a in core.apply].index(self)
        level = 0
        num_cycles = 0
        num_messages_in = 0
        num_messages_out = 0
        while not (yield tb.global_inactive):
            num_cycles += 1
            if (yield self.update_valid) and (yield self.update_ack) and (yield self.barrier_out):
                level += 1
                logger.info("{}: PE {} raised to level {}".format(num_cycles, pe_id, level))
            if (yield self.valid_in) and (yield self.ready) and (yield self.message_in_valid):
                num_messages_in += 1
            if (yield self.update_valid) and (yield self.update_ack) and not (yield self.barrier_out):
                logger.debug("{}: PE {} update out (sender={} origin={} hops={})".format(num_cycles, pe_id, (yield self.update_sender), (yield self.update_out.origin), (yield self.update_out.hops)))
                num_messages_out += 1
            yield
        logger.info("PE {}: {} cycles taken for {} supersteps. {} messages received, {} updates sent.".format(pe_id, num_cycles, level, num_messages_in, num_messages_out))
        logger.info("Average throughput: In: {:.1f} cycles/message Out: {:.1f} cycles/update".format(num_cycles/num_messages_in if num_messages_in!=0 else 0, num_cycles/num_messages_out if num_messages_out!=0 else 0))
