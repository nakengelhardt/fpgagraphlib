from migen import *
from migen.genlib.record import *

from bfs.interfaces import payload_layout, node_storage_layout

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

        self.message_out = Record(set_layout_parameters(payload_layout, **addresslayout.get_params()))
        self.message_sender = Signal(nodeidsize)
        self.message_valid = Signal()
        self.barrier_out = Signal()
        self.message_ack = Signal()

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
                self.state_out.parent.eq(self.message_in.parent)
            ),
            self.state_valid.eq(self.valid_in),
            self.nodeid_out.eq(self.nodeid_in),
            self.message_out.parent.eq(self.nodeid_in),
            self.message_sender.eq(self.nodeid_in),
            self.message_valid.eq(self.valid_in & ~visited & (self.nodeid_in != 0) & (self.message_in.parent != 0)),
            self.barrier_out.eq(self.barrier_in),
            self.state_barrier.eq(self.barrier_in),
            self.ready.eq(self.message_ack)
        ]

    def gen_selfcheck(self, tb, quiet=False):
        num_pe = len(tb.apply)
        level = 0
        num_cycles = 0
        while not (yield tb.global_inactive):
            num_cycles += 1
            if (yield self.barrier_out) and (yield self.message_ack):
                level += 1
            if (yield self.message_valid) and (yield self.message_ack):
                print("Node " + str((yield self.nodeid_out)) + " visited in round " + str(level) +". Parent: " + str((yield self.state_out.parent)))
            yield
        print(str(num_cycles) + " cycles taken.")