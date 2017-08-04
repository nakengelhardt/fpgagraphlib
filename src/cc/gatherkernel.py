from migen import *
from migen.genlib.record import *

from cc.interfaces import payload_layout, node_storage_layout

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

        self.comb+= [
            self.nodeid_out.eq(self.nodeid_in),
            If(self.state_in.color > self.message_in.color,
                self.state_out.color.eq(self.message_in.color),
                self.state_out.active.eq(1)
            ).Else(
                self.state_out.color.eq(self.state_in.color),
                self.state_out.active.eq(self.state_in.active)
            ),
            self.state_valid.eq(self.valid_in),
            self.ready.eq(self.state_ack)
        ]
