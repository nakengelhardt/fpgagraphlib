from migen import *

from migen.genlib.fifo import *
from migen.genlib.fsm import *

from core_interfaces import ApplyInterface, Message, _msg_layout

from functools import reduce
from operator import and_
import logging

class Barriercounter(Module):
    def __init__(self, config):
        self.apply_interface_in = ApplyInterface(name="apply_interface_in", **config.addresslayout.get_params())
        self.apply_interface_out = ApplyInterface(name="apply_interface_out", **config.addresslayout.get_params())
        self.change_rounds = Signal()

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

        self.sync += [
            self.all_from_pe[i].eq(self.num_from_pe[i] == self.num_expected_from_pe[i]) for i in range(num_pe)
        ]

        self.submodules.fsm = FSM()

        self.fsm.act("DEFAULT",
            If(self.apply_interface_out.ack,
                self.apply_interface_in.ack.eq(1),
                NextValue(self.apply_interface_out.msg.raw_bits(), self.apply_interface_in.msg.raw_bits()),
                NextValue(self.apply_interface_out.valid, self.apply_interface_in.valid & ~self.apply_interface_in.msg.barrier),
                If(self.apply_interface_in.valid,
                    If(self.apply_interface_in.msg.barrier,
                        NextValue(self.barrier_from_pe[config.addresslayout.pe_adr(self.apply_interface_in.msg.sender)], 1),
                        NextValue(self.num_expected_from_pe[config.addresslayout.pe_adr(self.apply_interface_in.msg.sender)], self.apply_interface_in.msg.dest_id),
                        NextState("CHK_BARRIER")
                    ).Else(
                        NextValue(self.num_from_pe[config.addresslayout.pe_adr(self.apply_interface_in.msg.sender)], self.num_from_pe[config.addresslayout.pe_adr(self.apply_interface_in.msg.sender)] + 1)
                    )
                )
            )
        )

        self.fsm.act("CHK_BARRIER",
            If(self.apply_interface_out.ack,
                NextValue(self.apply_interface_out.valid, 0)
            ),
            If(self.all_barriers_recvd,
                NextState("PASS_BARRIER")
            ).Else(
                NextState("DEFAULT")
            )
        )

        self.fsm.act("PASS_BARRIER",
            If(self.apply_interface_out.ack,
                If(self.all_messages_recvd,
                    self.change_rounds.eq(1),
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
                self.apply_interface_in.ack.eq(1),
                NextValue(self.apply_interface_out.msg.raw_bits(), self.apply_interface_in.msg.raw_bits()),
                NextValue(self.apply_interface_out.valid, self.apply_interface_in.valid),
                If(self.apply_interface_in.valid,
                    NextValue(self.num_from_pe[config.addresslayout.pe_adr(self.apply_interface_in.msg.sender)], self.num_from_pe[config.addresslayout.pe_adr(self.apply_interface_in.msg.sender)] + 1)
                ),
                NextState("CHK_BARRIER")
            )
        )
