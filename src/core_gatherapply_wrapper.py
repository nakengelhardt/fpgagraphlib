from migen import *

class GatherApplyWrapper(Module):
    def __init__(self, gatherkernel, applykernel):
        self.submodules.gatherkernel = gatherkernel
        self.submodules.applykernel = applykernel

        nodeidsize = len(gatherkernel.nodeid_in)

        self.level_in = Signal(32)
        self.nodeid_in = Signal(nodeidsize)
        self.sender_in = Signal(nodeidsize)
        self.message_in = Record(layout=gatherkernel.message_in.layout)
        self.message_in_valid = Signal()
        self.state_in = Record(layout=gatherkernel.state_in.layout)
        self.state_in_valid = Signal()
        self.round_in = Signal(len(applykernel.round_in))
        self.barrier_in = Signal()
        self.valid_in = Signal()
        self.ready = Signal()

        self.nodeid_out = Signal(nodeidsize)
        self.state_out = Record(layout=applykernel.state_out.layout)
        self.state_barrier = Signal()
        self.state_valid = Signal()
        self.state_ack = Signal()

        self.update_out = Record(layout=applykernel.update_out.layout)
        self.update_sender = Signal(nodeidsize)
        self.update_round = Signal(len(applykernel.round_in))
        self.barrier_out = Signal()
        self.update_valid = Signal()
        self.update_ack = Signal()

        self.kernel_error = Signal()



        self.comb += [
            self.gatherkernel.level_in.eq(self.level_in),
            self.gatherkernel.nodeid_in.eq(self.nodeid_in),
            self.gatherkernel.sender_in.eq(self.sender_in),
            self.gatherkernel.message_in.eq(self.message_in),
            self.gatherkernel.state_in.eq(self.state_in),
            self.gatherkernel.valid_in.eq(self.valid_in & self.message_in_valid & self.state_in_valid),
            self.gatherkernel.state_ack.eq(self.state_ack),

            self.applykernel.nodeid_in.eq(self.nodeid_in),
            self.applykernel.state_in.eq(self.state_in),
            self.applykernel.state_in_valid.eq(self.state_in_valid),
            self.applykernel.valid_in.eq(self.valid_in & ~self.message_in_valid),
            self.applykernel.round_in.eq(self.round_in),
            self.applykernel.barrier_in.eq(self.barrier_in),
            self.applykernel.update_ack.eq(self.update_ack),
            self.applykernel.state_ack.eq(self.state_ack),

            self.kernel_error.eq(self.applykernel.kernel_error),
            If(self.message_in_valid,
                self.ready.eq(self.gatherkernel.ready),
            ).Else(
                self.ready.eq(self.applykernel.ready)
            ),
            If(self.gatherkernel.state_valid,
                self.nodeid_out.eq(self.gatherkernel.nodeid_out),
                self.state_out.eq(self.gatherkernel.state_out),
                self.state_valid.eq(self.gatherkernel.state_valid)
            ).Else(
                self.nodeid_out.eq(self.applykernel.nodeid_out),
                self.state_out.eq(self.applykernel.state_out),
                self.state_valid.eq(self.applykernel.state_valid)
            ),
            self.state_barrier.eq(self.applykernel.state_barrier),

            self.update_out.eq(self.applykernel.update_out),
            self.update_sender.eq(self.applykernel.update_sender),
            self.update_valid.eq(self.applykernel.update_valid),
            self.update_round.eq(self.applykernel.update_round),
            self.barrier_out.eq(self.applykernel.barrier_out)
        ]
