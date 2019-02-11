from migen import *
from migen.genlib.record import *

from sssp.interfaces import message_layout, node_storage_layout

class GatherKernel(Module):
    def __init__(self, config):
        nodeidsize = config.addresslayout.nodeidsize

        self.nodeid_in = Signal(nodeidsize)
        self.sender_in = Signal(nodeidsize)
        self.message_in = Record(set_layout_parameters(message_layout, **config.addresslayout.get_params()))
        self.state_in = Record(set_layout_parameters(node_storage_layout, **config.addresslayout.get_params()))
        self.valid_in = Signal()
        self.ready = Signal()

        self.nodeid_out = Signal(nodeidsize)
        self.state_out = Record(set_layout_parameters(node_storage_layout, **config.addresslayout.get_params()))
        self.state_valid = Signal()
        self.state_ack = Signal()


        self.comb += [
            If(self.state_in.dist > self.message_in.dist,
                self.state_out.dist.eq(self.message_in.dist),
                self.state_out.parent.eq(self.sender_in),
                self.state_out.active.eq(1),
            ).Else(
                self.state_out.dist.eq(self.state_in.dist),
                self.state_out.parent.eq(self.state_in.parent),
                self.state_out.active.eq(self.state_in.active),
            ),
            self.nodeid_out.eq(self.nodeid_in),
            self.state_valid.eq(self.valid_in),
            self.ready.eq(self.state_ack)
        ]
