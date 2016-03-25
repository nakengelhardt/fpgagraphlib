from migen import *
from migen.genlib.record import *

from cc.interfaces import payload_layout, node_storage_layout

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
        self.message_round = Signal()
        self.barrier_out = Signal()
        self.message_ack = Signal()

        ###

        self.comb+= [
            If(self.state_in.color > self.message_in.color,
                self.state_out.color.eq(self.message_in.color),
                self.message_valid.eq(self.valid_in)
            ).Else(
                self.state_out.color.eq(self.state_in.color),
                self.message_valid.eq(0)
            ),
            self.message_out.color.eq(self.message_in.color),
            self.state_valid.eq(self.valid_in),
            self.nodeid_out.eq(self.nodeid_in),
            self.message_sender.eq(self.nodeid_in),
            self.message_round.eq(self.level_in[0]),
            self.barrier_out.eq(self.barrier_in),
            self.state_barrier.eq(self.barrier_in),
            self.ready.eq(self.message_ack)
        ]

    def gen_selfcheck(self, tb, quiet=False):
        num_pe = len(tb.apply)
        pe_id = [a.applykernel for a in tb.apply].index(self)
        level = 0
        num_cycles = 0
        num_messages_in = 0
        num_messages_out = 0
        while not (yield tb.global_inactive):
            num_cycles += 1
            if (yield self.barrier_out) and (yield self.message_ack):
                level += 1
            if (yield self.valid_in) and (yield self.ready):
                if (yield self.barrier_in):
                    print("Warning: Simultaneous valid / barrier!")
                num_messages_in += 1
                if not quiet:
                    print("State in: {} / Message in: {} / {}update".format((yield self.state_in.color), (yield self.message_in.color), "" if (yield self.message_valid) else "no "))
            if (yield self.message_valid) and (yield self.message_ack):
                num_messages_out += 1
                if not quiet:
                    print("Node " + str((yield self.nodeid_out)) + " updated in round " + str(level) +". New color: " + str((yield self.message_out.color)))
            yield
        print("PE {}: {} cycles taken for {} supersteps. {} messages received, {} messages sent.".format(pe_id, num_cycles, level, num_messages_in, num_messages_out))
        print("Average throughput: In: {:.1f} cycles/message Out: {:.1f} cycles/message".format(num_cycles/num_messages_in if num_messages_in!=0 else 0, num_cycles/num_messages_out if num_messages_out!=0 else 0))
