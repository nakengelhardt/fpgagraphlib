from migen import *
from migen.genlib.record import *

from bfs.interfaces import payload_layout, node_storage_layout

import logging

class ApplyKernel(Module):
    def __init__(self, addresslayout):
        nodeidsize = addresslayout.nodeidsize

        self.level_in = Signal(32)
        self.nodeid_in = Signal(nodeidsize)
        self.sender_in = Signal(nodeidsize)
        self.message_in = Record(set_layout_parameters(payload_layout, **addresslayout.get_params()))
        self.state_in = Record(set_layout_parameters(node_storage_layout, **addresslayout.get_params()))
        self.valid_in = Signal()
        self.barrier_in = Signal()
        self.ready = Signal()

        self.nodeid_out = Signal(nodeidsize)
        self.state_out = Record(set_layout_parameters(node_storage_layout, **addresslayout.get_params()))
        self.state_valid = Signal()
        self.state_barrier = Signal()

        self.update_out = Record(set_layout_parameters(payload_layout, **addresslayout.get_params()))
        self.update_sender = Signal(nodeidsize)
        self.update_valid = Signal()
        self.update_round = Signal(addresslayout.channel_bits)
        self.barrier_out = Signal()
        self.update_ack = Signal()

        ###

        # find out if we have an update
        # assumes 0 is not a valid nodeID
        # if we read 0, node did not have a parent yet, and we want to write one now.
        # some sanity checks for sending & receiving node not being 0
        visited = Signal()
        self.comb += visited.eq(self.state_in.parent != 0)

        self.comb+= [
            If(visited,
                self.state_out.parent.eq(self.state_in.parent)
            ).Else(
                self.state_out.parent.eq(self.sender_in)
            ),
            self.state_valid.eq(self.valid_in),
            self.nodeid_out.eq(self.nodeid_in),
            self.update_sender.eq(self.nodeid_in),
            self.update_round.eq(self.level_in[0:addresslayout.channel_bits]),
            self.update_valid.eq(self.valid_in & ~visited & (self.nodeid_in != 0) & (self.sender_in != 0)),
            self.barrier_out.eq(self.barrier_in),
            self.state_barrier.eq(self.barrier_in),
            self.ready.eq(self.update_ack)
        ]

    def gen_selfcheck(self, tb):
        logger = logging.getLogger("simulation.applykernel")
        num_pe = len(tb.apply)
        pe_id = [a.applykernel for a in tb.apply].index(self)
        level = 0
        num_cycles = 0
        num_messages_in = 0
        num_messages_out = 0
        while not (yield tb.global_inactive):
            num_cycles += 1
            if (yield self.barrier_out) and (yield self.update_ack):
                level += 1
                logger.info("{}: PE {} raised to level {}".format(num_cycles, pe_id, level))
            if (yield self.valid_in) and (yield self.ready):
                num_messages_in += 1
            if (yield self.update_valid) and (yield self.update_ack):
                num_messages_out += 1
                logger.debug("Node " + str((yield self.nodeid_out)) + " visited in round " + str(level) +". Parent: " + str((yield self.state_out.parent)))
            yield
        logger.info("PE {}: {} cycles taken for {} supersteps. {} messages received, {} messages sent.".format(pe_id, num_cycles, level, num_messages_in, num_messages_out))
        logger.info("Average throughput: In: {:.1f} cycles/message Out: {:.1f} cycles/message".format(num_cycles/num_messages_in if num_messages_in!=0 else 0, num_cycles/num_messages_out if num_messages_out!=0 else 0))
