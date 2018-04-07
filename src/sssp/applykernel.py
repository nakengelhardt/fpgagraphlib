from migen import *
from migen.genlib.record import *

from sssp.interfaces import update_layout, node_storage_layout

class ApplyKernel(Module):
    def __init__(self, config):
        nodeidsize = config.addresslayout.nodeidsize

        self.nodeid_in = Signal(nodeidsize)
        self.state_in = Record(set_layout_parameters(node_storage_layout, **config.addresslayout.get_params()))
        self.valid_in = Signal()
        self.round_in = Signal(config.addresslayout.channel_bits)
        self.barrier_in = Signal()
        self.ready = Signal()

        self.nodeid_out = Signal(nodeidsize)
        self.state_out = Record(set_layout_parameters(node_storage_layout, **config.addresslayout.get_params()))
        self.state_valid = Signal()
        self.state_barrier = Signal()

        self.update_out = Record(set_layout_parameters(update_layout, **config.addresslayout.get_params()))
        self.update_sender = Signal(nodeidsize)
        self.update_valid = Signal()
        self.update_round = Signal(config.addresslayout.channel_bits)
        self.barrier_out = Signal()
        self.update_ack = Signal()

        self.kernel_error = Signal()

        ###

        self.comb+= [
            self.state_out.dist.eq(self.state_in.dist),
            self.state_out.parent.eq(self.state_in.parent),
            self.state_out.active.eq(0),
            self.update_out.dist.eq(self.state_in.dist),
            self.state_valid.eq(self.valid_in),
            self.nodeid_out.eq(self.nodeid_in),
            self.update_sender.eq(self.nodeid_in),
            self.update_round.eq(self.round_in),
            self.update_valid.eq(self.valid_in),
            self.barrier_out.eq(self.barrier_in),
            self.state_barrier.eq(self.barrier_in),
            self.ready.eq(self.update_ack)
        ]

    def gen_selfcheck(self, tb, quiet=True):
        num_pe = tb.config.addresslayout.num_pe
        pe_id = [a.applykernel for core in tb.cores for a in core.apply].index(self)
        level = 0
        num_cycles = 0
        num_messages_out = 0
        while not (yield tb.global_inactive):
            num_cycles += 1
            if (yield self.barrier_out) and (yield self.update_ack):
                level += 1
            if (yield self.valid_in) and (yield self.ready):
                if (yield self.barrier_in):
                    print("Warning: Simultaneous valid / barrier!")
            if (yield self.update_valid) and (yield self.update_ack):
                num_messages_out += 1
                if not quiet:
                    print("Node " + str((yield self.nodeid_out)) + " updated in round " + str(level) +". New distance: " + str((yield self.update_out.dist)))
            yield
        print("PE {}: {} cycles taken for {} supersteps. {} messages sent.".format(pe_id, num_cycles, level, num_messages_out))
        print("Average throughput: Out: {:.1f} cycles/message".format(num_cycles/num_messages_out if num_messages_out!=0 else 0))
