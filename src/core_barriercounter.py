from migen import *

from migen.genlib.fifo import *
from migen.genlib.fsm import *

from core_interfaces import ApplyInterface, Message, _msg_layout
from util.recordfifo import *

from functools import reduce
from operator import and_
import logging

class Barriercounter(Module):
    def __init__(self, config):
        self.apply_interface_in = ApplyInterface(name="barriercounter_in", **config.addresslayout.get_params())
        self.apply_interface_out = ApplyInterface(name="barriercounter_out", **config.addresslayout.get_params())
        self.round_accepting = Signal(config.addresslayout.channel_bits)

        apply_interface_in_fifo = InterfaceFIFO(layout=self.apply_interface_in.layout, depth=2)
        self.submodules += apply_interface_in_fifo
        self.comb += self.apply_interface_in.connect(apply_interface_in_fifo.din)

        num_pe = config.addresslayout.num_pe

        self.barrier_from_pe = Array(Signal() for _ in range(num_pe))
        self.num_from_pe = Array(Signal(config.addresslayout.nodeidsize) for _ in range(num_pe))
        self.num_expected_from_pe = Array(Signal(config.addresslayout.nodeidsize) for _ in range(num_pe))
        self.all_from_pe = Array(Signal() for _ in range (num_pe))
        self.all_messages_recvd = Signal()
        self.all_barriers_recvd = Signal()

        self.comb += [
            self.all_barriers_recvd.eq(reduce(and_, self.barrier_from_pe)),
            self.all_messages_recvd.eq(reduce(and_, self.all_from_pe)),
        ]

        self.comb += [
            self.all_from_pe[i].eq(self.num_from_pe[i] == self.num_expected_from_pe[i]) for i in range(num_pe)
        ]

        halt = Signal()

        sender_pe = config.addresslayout.pe_adr(apply_interface_in_fifo.dout.msg.sender)

        self.submodules.fsm = FSM()

        self.fsm.act("DEFAULT",
            If(self.apply_interface_out.ack,
                apply_interface_in_fifo.dout.ack.eq(1),
                NextValue(self.apply_interface_out.msg.raw_bits(), apply_interface_in_fifo.dout.msg.raw_bits()),
                NextValue(self.apply_interface_out.valid, apply_interface_in_fifo.dout.valid & ~apply_interface_in_fifo.dout.msg.barrier),
                If(apply_interface_in_fifo.dout.valid,
                    If(apply_interface_in_fifo.dout.msg.barrier,
                        NextValue(self.barrier_from_pe[sender_pe], 1),
                        NextValue(self.num_expected_from_pe[sender_pe], apply_interface_in_fifo.dout.msg.dest_id),
                        If(~apply_interface_in_fifo.dout.msg.halt,
                            NextValue(halt, 0)
                        ),
                        NextState("CHK_BARRIER")
                    ).Else(
                        NextValue(self.num_from_pe[sender_pe], self.num_from_pe[sender_pe] + 1)
                    )
                )
            )
        )

        self.fsm.act("CHK_BARRIER",
            apply_interface_in_fifo.dout.ack.eq(0),
            If(self.apply_interface_out.ack,
                NextValue(self.apply_interface_out.valid, 0),
                If(self.all_barriers_recvd,
                    NextState("PASS_BARRIER")
                ).Else(
                    NextState("DEFAULT")
                )
            )
        )

        self.fsm.act("PASS_BARRIER",
            apply_interface_in_fifo.dout.ack.eq(0),
            If(self.apply_interface_out.ack,
                If(self.all_messages_recvd,
                    If(self.round_accepting < config.addresslayout.num_channels - 1,
                        NextValue(self.round_accepting, self.round_accepting + 1)
                    ).Else(
                        NextValue(self.round_accepting, 0)
                    ),
                    NextValue(halt, 1),
                    NextValue(self.apply_interface_out.msg.halt, halt),
                    NextValue(self.apply_interface_out.msg.barrier, 1),
                    NextValue(self.apply_interface_out.valid, 1),
                    [NextValue(self.barrier_from_pe[i], 0) for i in range(num_pe)],
                    [NextValue(self.num_from_pe[i], 0) for i in range(num_pe)],
                    NextState("DEFAULT")
                ).Else(
                    NextValue(self.apply_interface_out.valid, 0),
                    NextState("WAIT_FOR_STRAGGLER")
                )
            )
        )

        self.fsm.act("WAIT_FOR_STRAGGLER",
            If(self.apply_interface_out.ack,
                apply_interface_in_fifo.dout.ack.eq(1),
                NextValue(self.apply_interface_out.msg.raw_bits(), apply_interface_in_fifo.dout.msg.raw_bits()),
                NextValue(self.apply_interface_out.valid, apply_interface_in_fifo.dout.valid),
                If(apply_interface_in_fifo.dout.valid,
                    NextValue(self.num_from_pe[sender_pe], self.num_from_pe[sender_pe] + 1),
                    NextState("CHK_BARRIER") #this gratuitously checks all_barriers_recvd again, but we need to wait an extra cycle for all_messages_recvd to be updated
                )
            )
        )
