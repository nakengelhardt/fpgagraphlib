from migen import *
from migen.genlib.record import *
from tbsupport import convert_32b_int_to_float, convert_int_to_record

from pr.interfaces import payload_layout, node_storage_layout
from faddsub import FAddSub
from fmul import FMul

import logging

class GatherKernel(Module):
    def __init__(self, config):
        nodeidsize = config.addresslayout.nodeidsize
        floatsize = config.addresslayout.floatsize

        self.level_in = Signal(32)
        self.nodeid_in = Signal(nodeidsize)
        self.sender_in = Signal(nodeidsize)
        self.message_in = Record(set_layout_parameters(payload_layout, **config.addresslayout.get_params()))
        self.state_in = Record(set_layout_parameters(node_storage_layout, **config.addresslayout.get_params()))
        self.valid_in = Signal()
        self.ready = Signal()

        self.nodeid_out = Signal(nodeidsize)
        self.state_out = Record(set_layout_parameters(node_storage_layout, **config.addresslayout.get_params()))
        self.state_valid = Signal()
        self.state_ack = Signal()


        p1_ce = Signal()

        self.comb += self.ready.eq(p1_ce)
        self.comb += p1_ce.eq(self.state_ack)

        # First part: add weight to sum
        # 4 cycles latency
        n_nodeid = Signal(nodeidsize)
        n_sum = Signal(floatsize)
        n_nrecvd = Signal(nodeidsize)
        n_nneighbors = Signal(nodeidsize)
        n_barrier = Signal()
        n_round = Signal(config.addresslayout.channel_bits)
        n_valid = Signal()
        n_allrecvd = Signal()
        n_init = Signal()
        n_notend = Signal()

        self.submodules.add1 = FAddSub()
        self.comb += [
            self.add1.a.eq(self.state_in.sum),
            self.add1.b.eq(self.message_in.weight),
            self.add1.valid_i.eq(self.valid_in),
            n_sum.eq(self.add1.r),
            n_valid.eq(self.add1.valid_o),
            self.add1.ce.eq(p1_ce)
        ]

        i_nrecvd = [Signal(nodeidsize) for _ in range(3)]
        i_nneighbors = [Signal(nodeidsize) for _ in range(3)]
        i_round = [Signal(config.addresslayout.channel_bits) for _ in range(3)]
        i_nodeid = [Signal(nodeidsize) for _ in range(3)]
        i_init = [Signal() for _ in range(3)]
        i_notend = [Signal() for _ in range(3)]

        self.sync += If(p1_ce, [
            i_nrecvd[0].eq(self.state_in.nrecvd + 1),
            i_nneighbors[0].eq(self.state_in.nneighbors),
            i_round[0].eq(self.level_in[0:config.addresslayout.channel_bits]),
            i_nodeid[0].eq(self.nodeid_in),
            i_init[0].eq(self.level_in == 0),
            i_notend[0].eq(self.level_in < config.total_pr_rounds)
        ] + [
            i_nrecvd[i].eq(i_nrecvd[i-1]) for i in range(1,3)
        ] + [
            i_nneighbors[i].eq(i_nneighbors[i-1]) for i in range(1,3)
        ] + [
            i_round[i].eq(i_round[i-1]) for i in range(1,3)
        ] + [
            i_nodeid[i].eq(i_nodeid[i-1]) for i in range(1,3)
        ] + [
            i_init[i].eq(i_init[i-1]) for i in range(1,3)
        ] + [
            i_notend[i].eq(i_notend[i-1]) for i in range(1,3)
        ] + [
            n_nrecvd.eq(i_nrecvd[-1]),
            n_nneighbors.eq(i_nneighbors[-1]),
            n_round.eq(i_round[-1]),
            n_nodeid.eq(i_nodeid[-1]),
            n_allrecvd.eq(i_nrecvd[-1] == i_nneighbors[-1]),
            n_init.eq(i_init[-1]),
            n_notend.eq(i_notend[-1])
        ])

        self.comb += [
            self.nodeid_out.eq(n_nodeid),
            self.state_out.nneighbors.eq(n_nneighbors),
            If(n_init,
                self.state_out.nrecvd.eq(n_nneighbors),
                self.state_out.sum.eq(0)
            ).Else(
                self.state_out.nrecvd.eq(n_nrecvd),
                self.state_out.sum.eq(n_sum)
            ),
            self.state_valid.eq(n_valid),
            self.state_out.active.eq(n_notend)
        ]
