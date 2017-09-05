from migen import *

from migen.genlib.roundrobin import *

from functools import reduce
from operator import and_
import logging

from recordfifo import *
from core_interfaces import _network_layout, ApplyInterface, NetworkInterface
from core_barriercounter import Barriercounter

class Arbiter(Module):
    def __init__(self, pe_id, config):
        self.network_interface_in = NetworkInterface(name="left_in", **config.addresslayout.get_params())
        self.network_interface_out = NetworkInterface(name="right_out", **config.addresslayout.get_params())
        self.local_interface_in = NetworkInterface(name="local_in", **config.addresslayout.get_params())
        local_interface_out = NetworkInterface(name="local_out", **config.addresslayout.get_params())

        self.apply_interface_out = ApplyInterface(**config.addresslayout.get_params())
        self.start_message = ApplyInterface(**config.addresslayout.get_params())
        self.start_message.select = Signal()

        self.network_round = Signal(config.addresslayout.channel_bits)
        self.round_accepting = Signal(config.addresslayout.channel_bits)

        mux_interface = NetworkInterface(**config.addresslayout.get_params())


        inject = Signal()
        self.comb += [
            inject.eq(self.local_interface_in.msg.roundpar == self.network_round),
            If(self.network_interface_in.valid & (self.network_interface_in.msg.roundpar == self.network_round),
                self.network_interface_in.connect(mux_interface)
            ).Elif(inject,
                self.local_interface_in.connect(mux_interface)
            )
        ]



        self.comb += [
            If(mux_interface.dest_pe == pe_id,
                mux_interface.connect(local_interface_out)
            ).Else(
                mux_interface.connect(self.network_interface_out)
            )
        ]

        self.submodules.barriercounter = Barriercounter(config)

        self.comb += [
            local_interface_out.msg.connect(self.barriercounter.apply_interface_in.msg),
            self.barriercounter.apply_interface_in.valid.eq(local_interface_out.valid),
            local_interface_out.ack.eq(self.barriercounter.apply_interface_in.ack),
            If(self.start_message.select,
                self.start_message.connect(self.apply_interface_out)
            ).Else(
                self.barriercounter.apply_interface_out.connect(self.apply_interface_out)
            ),
            self.round_accepting.eq(self.barriercounter.round_accepting)
        ]

    def gen_selfcheck(self, tb):
        yield

class Network(Module):
    def __init__(self, config):
        num_pe = config.addresslayout.num_pe
        num_nodes_per_pe = config.addresslayout.num_nodes_per_pe

        self.apply_interface = [ApplyInterface(name="network_out", **config.addresslayout.get_params()) for _ in range(num_pe)]
        self.network_interface = [NetworkInterface(name="network_in", **config.addresslayout.get_params()) for _ in range(num_pe)]

        fifos = [InterfaceFIFO(layout=set_layout_parameters(_network_layout, **config.addresslayout.get_params()), depth=8) for i in range(num_pe)]
        self.submodules.fifos = fifos
        self.submodules.arbiter = [Arbiter(sink, config) for sink in range(num_pe)]

        for i in range(num_pe):
            j = (i + 1) % num_pe

            self.comb += [
                self.arbiter[i].network_interface_out.connect(fifos[i].din),
                fifos[i].dout.connect(self.arbiter[j].network_interface_in),
                self.network_interface[i].connect(self.arbiter[i].local_interface_in),
                self.arbiter[i].apply_interface_out.connect(self.apply_interface[i])
            ]

        network_round = Signal(config.addresslayout.channel_bits)
        next_round = Signal(config.addresslayout.channel_bits)
        proceed = Signal()

        self.comb += [
            proceed.eq(reduce(and_, [a.round_accepting == next_round for a in self.arbiter])),
            If(network_round < config.addresslayout.num_channels - 1,
                next_round.eq(network_round + 1)
            ).Else(
                next_round.eq(0)
            ),
            [self.arbiter[i].network_round.eq(network_round) for i in range(num_pe)]
        ]

        self.sync += If(proceed,
            network_round.eq(next_round)
        )
