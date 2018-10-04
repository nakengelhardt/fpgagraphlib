from migen import *
from migen.genlib.roundrobin import *

from functools import reduce
from operator import and_

from recordfifo import *
from core_interfaces import *
from inverted_barriercounter import Barriercounter

class SimpleRoundrobin(Module):
    def __init__(self, config, in_array):
        self.apply_interface_out = ApplyInterface(name="mux_apply_interface_out", **config.addresslayout.get_params())
        self.current_round = Signal(config.addresslayout.channel_bits)

        if len(in_array) == 1:
            self.comb += in_array[0].connect(self.apply_interface_out)
        else:
            self.submodules.roundrobin = RoundRobin(len(in_array), switch_policy=SP_CE)
            # arrays for choosing incoming fifo to use
            array_msg = Array(interface.msg.raw_bits() for interface in in_array)
            array_ack = Array(interface.ack for interface in in_array)
            array_valid = Array(interface.valid for interface in in_array)
            array_round = Array(interface.msg.roundpar for interface in in_array)

            self.comb += [
                self.apply_interface_out.msg.raw_bits().eq(array_msg[self.roundrobin.grant]),
                self.apply_interface_out.valid.eq(array_valid[self.roundrobin.grant] & (array_round[self.roundrobin.grant] == self.current_round)),
                array_ack[self.roundrobin.grant].eq(self.apply_interface_out.ack & (array_round[self.roundrobin.grant] == self.current_round)),
                [self.roundrobin.request[i].eq(array_valid[i] & (array_round[i] == self.current_round)) for i in range(len(in_array))],
                self.roundrobin.ce.eq(1)
            ]

class UpdateNetwork(Module):
    def __init__(self, config):
        num_pe = config.addresslayout.num_pe
        self.apply_interface_in = [ApplyInterface(name="network_in", **config.addresslayout.get_params()) for _ in range(num_pe)]
        self.scatter_interface_out = [ScatterInterface(name="network_out", **config.addresslayout.get_params()) for _ in range(num_pe)]

        self.submodules.srr = SimpleRoundrobin(config, self.apply_interface_in)
        self.submodules.bc = Barriercounter(config)

        self.comb += [
            self.srr.apply_interface_out.connect(self.bc.apply_interface_in),
            self.srr.current_round.eq(self.bc.round_accepting)
        ]

        transaction_ok = Signal()
        computation_end = Signal()
        self.inactive = Signal()

        self.comb += [
            computation_end.eq(self.bc.apply_interface_out.valid & self.bc.apply_interface_out.msg.barrier & self.bc.apply_interface_out.msg.halt),
            transaction_ok.eq(reduce(and_, [s.ack for s in self.scatter_interface_out])),
            self.bc.apply_interface_out.ack.eq(transaction_ok | computation_end)
        ]

        for i in range(num_pe):
            self.comb += [
                self.scatter_interface_out[i].barrier.eq(self.bc.apply_interface_out.msg.barrier),
                self.scatter_interface_out[i].roundpar.eq(self.bc.apply_interface_out.msg.roundpar),
                self.scatter_interface_out[i].sender.eq(self.bc.apply_interface_out.msg.sender),
                self.scatter_interface_out[i].payload.eq(self.bc.apply_interface_out.msg.payload),
                self.scatter_interface_out[i].valid.eq(self.bc.apply_interface_out.valid & transaction_ok & ~computation_end),
            ]


        self.sync += If(self.bc.apply_interface_out.valid & computation_end,
            self.inactive.eq(1)
        )
