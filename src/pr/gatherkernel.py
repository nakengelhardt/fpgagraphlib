from migen import *
from migen.genlib.record import *
from tbsupport import convert_32b_int_to_float, convert_int_to_record

from pr.interfaces import *
from faddsub import FAddSub
from fmul import FMul

import logging

class GatherKernel(Module):
    # PageRank formula:
    # PR_(i+1)(u) = (1-d)/N + d * sum(PR_i(v)/degree(v) for v in neighbors(u))
    # each message contains PR_i(v)/degree(v)
    # this gather phase performs the sum
    def __init__(self, config):
        nodeidsize = config.addresslayout.nodeidsize
        floatsize = config.addresslayout.floatsize

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

        self.comb += self.ready.eq(self.state_ack)

        # First part: add weight to sum
        # 4 cycles latency
        self.submodules.add = FAddSub()
        self.comb += [
            self.add.a.eq(self.state_in.sum),
            self.add.b.eq(self.message_in.rank),
            self.add.valid_i.eq(self.valid_in),
            self.state_out.sum.eq(self.add.r),
            self.state_valid.eq(self.add.valid_o),
            self.add.ce.eq(self.state_ack),
            self.state_out.active.eq(1)
        ]

        # intermediate register stages for non-involved signals
        i_nrecvd = [Signal(nodeidsize) for _ in range(3)]
        i_nneighbors = [Signal(nodeidsize) for _ in range(3)]
        i_nodeid = [Signal(nodeidsize) for _ in range(3)]
        i_notend = [Signal() for _ in range(3)]

        self.sync += If(self.state_ack, [
            i_nrecvd[0].eq(self.state_in.nrecvd + 1),
            i_nneighbors[0].eq(self.state_in.nneighbors),
            i_nodeid[0].eq(self.nodeid_in)
        ] + [
            i_nrecvd[i].eq(i_nrecvd[i-1]) for i in range(1,3)
        ] + [
            i_nneighbors[i].eq(i_nneighbors[i-1]) for i in range(1,3)
        ] + [
            i_nodeid[i].eq(i_nodeid[i-1]) for i in range(1,3)
        ] + [
            self.state_out.nrecvd.eq(i_nrecvd[-1]),
            self.state_out.nneighbors.eq(i_nneighbors[-1]),
            self.nodeid_out.eq(i_nodeid[-1])
        ])
