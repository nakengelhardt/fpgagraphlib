from migen import *
from migen.genlib.record import *

from bfs.interfaces import payload_layout, node_storage_layout

import logging

class GatherKernel(Module):
    def __init__(self, addresslayout):
        nodeidsize = addresslayout.nodeidsize

        self.level_in = Signal(32)
        self.nodeid_in = Signal(nodeidsize)
        self.sender_in = Signal(nodeidsize)
        self.message_in = Record(set_layout_parameters(payload_layout, **addresslayout.get_params()))
        self.state_in = Record(set_layout_parameters(node_storage_layout, **addresslayout.get_params()))
        self.valid_in = Signal()
        self.ready = Signal()

        self.nodeid_out = Signal(nodeidsize)
        self.state_out = Record(set_layout_parameters(node_storage_layout, **addresslayout.get_params()))
        self.state_valid = Signal()
        self.state_ack = Signal()

        # find out if we have an update
        # assumes 0 is not a valid nodeID
        # if we read 0, node did not have a parent yet, and we want to write one now.
        visited = Signal()
        self.comb += visited.eq(self.state_in.parent != 0)

        self.comb += [
            If(visited,
                self.state_out.parent.eq(self.state_in.parent),
                self.state_out.active.eq(self.state_in.active)
            ).Else(
                self.state_out.parent.eq(self.sender_in),
                self.state_out.active.eq(1)
            ),
            self.state_valid.eq(self.valid_in),
            self.nodeid_out.eq(self.nodeid_in),
            self.ready.eq(self.state_ack)
        ]
