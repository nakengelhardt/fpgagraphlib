from migen import *
from migen.genlib.record import *

from sssp.interfaces import message_layout, update_layout, edge_storage_layout

class ScatterKernel(Module):
    def __init__(self, addresslayout):

        self.update_in = Record(set_layout_parameters(update_layout, **addresslayout.get_params()))
        self.num_neighbors_in = Signal(addresslayout.edgeidsize)
        self.neighbor_in = Signal(addresslayout.nodeidsize)
        self.edgedata_in = Record(set_layout_parameters(edge_storage_layout, **addresslayout.get_params()))
        self.sender_in = Signal(addresslayout.nodeidsize)
        self.round_in = Signal(addresslayout.channel_bits)
        self.barrier_in = Signal()
        self.valid_in = Signal()
        self.ready = Signal()

        self.message_out = Record(set_layout_parameters(message_layout, **addresslayout.get_params()))
        self.neighbor_out = Signal(addresslayout.nodeidsize)
        self.sender_out = Signal(addresslayout.nodeidsize)
        self.round_out = Signal(addresslayout.channel_bits)
        self.valid_out = Signal()
        self.message_ack = Signal()
        self.barrier_out = Signal()

        ####

        self.sync += If(self.message_ack,
            self.message_out.dist.eq(self.update_in.dist
                + self.edgedata_in.dist),
            self.neighbor_out.eq(self.neighbor_in),
            self.sender_out.eq(self.sender_in),
            self.round_out.eq(self.round_in),
            self.valid_out.eq(self.valid_in),
            self.barrier_out.eq(self.barrier_in)
        )


        self.comb += [
            self.ready.eq(self.message_ack)
        ]

    def gen_selfcheck(self, tb, quiet=True):
        while not (yield tb.global_inactive):
            if (yield self.valid_in) and (yield self.ready):
                if (yield self.barrier_in):
                    print("Warning: Simultaneous valid / barrier!")
                if not quiet:
                    print("Message in: {} / Edge in: {}".format((yield self.message_in.dist), (yield self.edgedata_in.dist)))
            yield
