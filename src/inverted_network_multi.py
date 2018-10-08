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

class Broadcaster(Module):
    def __init__(self, config, out_array):
        self.apply_interface_in = ApplyInterface(name="mux_apply_interface_in", **config.addresslayout.get_params())
        if len(out_array) == 1:
            self.comb += self.apply_interface_in.connect(out_array[0])
        else:
            transaction_ok = Signal()
            self.comb += [
                transaction_ok.eq(reduce(and_, [out.ack for out in out_array])),
                [self.apply_interface_in.connect(out, omit={'valid', 'ack'}) for out in out_array],
                [out.valid.eq(self.apply_interface_in.valid & transaction_ok) for out in out_array],
                self.apply_interface_in.ack.eq(transaction_ok)
            ]

class UpdateNetwork(Module):
    def __init__(self, config):
        num_pe = config.addresslayout.num_pe_per_fpga
        num_fpga = config.addresslayout.num_fpga
        self.apply_interface_in = [ApplyInterface(name="network_in", **config.addresslayout.get_params()) for _ in range(num_pe)]
        self.scatter_interface_out = [ScatterInterface(name="network_out", **config.addresslayout.get_params()) for _ in range(num_pe)]

        self.external_network_interface_in = [ApplyInterface(name="ext_network_in", **config.addresslayout.get_params()) for _ in range(num_fpga - 1)]
        self.external_network_interface_out = [ApplyInterface(name="ext_network_out", **config.addresslayout.get_params()) for _ in range(num_fpga - 1)]

        self.submodules.srr = SimpleRoundrobin(config, self.apply_interface_in)
        self.submodules.ext_srr = SimpleRoundrobin(config, self.external_network_interface_in)

        self.submodules.fifos = [InterfaceFIFO(layout=self.apply_interface_in[0].layout, depth=8, name="link_{}".format(sink)) for sink in range(num_pe)]

        self.submodules.ext_fifos = [InterfaceFIFO(layout=self.apply_interface_in[0].layout, depth=8, name="ext_link_{}".format(sink)) for sink in range(num_fpga - 1)]

        self.submodules.broadcaster = Broadcaster(config, [fifo.din for fifo in self.fifos])
        self.submodules.ext_broadcaster = Broadcaster(config, [fifo.din for fifo in self.ext_fifos])

        # Two inputs and two outputs (internal and external)
        # inputs from internal PEs are sent to both internal and external
        # inputs from external PEs are only sent to internal (otherwise broadcast loop occurs)
        transaction_ok = Signal()
        self.comb += [
            transaction_ok.eq(self.broadcaster.apply_interface_in.ack & self.ext_broadcaster.apply_interface_in.ack),
            # prioritize receiving over sending on FPGA level
            If(self.ext_srr.apply_interface_out.valid,
                self.ext_srr.apply_interface_out.connect(self.broadcaster.apply_interface_in)
            ).Else(
                self.srr.apply_interface_out.connect(self.broadcaster.apply_interface_in, omit={'valid', 'ack'}),
                self.srr.apply_interface_out.connect(self.ext_broadcaster.apply_interface_in, omit={'valid', 'ack'}),
                self.broadcaster.apply_interface_in.valid.eq(self.srr.apply_interface_out.valid & transaction_ok),
                self.ext_broadcaster.apply_interface_in.valid.eq(self.srr.apply_interface_out.valid & transaction_ok),
                self.srr.apply_interface_out.ack.eq(transaction_ok)
            )
        ]

        # connect end of fifo to barriercounter and barriercounter to local output
        # detect local end of computation at each barriercounter and don't propagate barrier message
        self.submodules.bc = [Barriercounter(config) for _ in range(num_pe)]
        computation_end = [Signal() for _ in range(num_pe)]

        for i in range(num_pe):
            halt = Signal()
            self.comb += [
                self.fifos[i].dout.connect(self.bc[i].apply_interface_in),
                self.scatter_interface_out[i].barrier.eq(self.bc[i].apply_interface_out.msg.barrier),
                self.scatter_interface_out[i].roundpar.eq(self.bc[i].apply_interface_out.msg.roundpar),
                self.scatter_interface_out[i].sender.eq(self.bc[i].apply_interface_out.msg.sender),
                self.scatter_interface_out[i].payload.eq(self.bc[i].apply_interface_out.msg.payload),
                halt.eq(self.bc[i].apply_interface_out.valid & self.bc[i].apply_interface_out.msg.barrier & self.bc[i].apply_interface_out.msg.halt),
                self.scatter_interface_out[i].valid.eq(self.bc[i].apply_interface_out.valid & ~halt),
                self.bc[i].apply_interface_out.ack.eq(self.scatter_interface_out[i].ack | halt)
            ]

            self.sync += If(halt,
                computation_end[i].eq(1)
            )

        for i in range(num_fpga - 1):
            self.comb += [
                self.ext_fifos[i].dout.connect(self.external_network_interface_out[i])
            ]

        # do switchover to next round
        network_round = Signal(config.addresslayout.channel_bits)
        next_round = Signal(config.addresslayout.channel_bits)
        proceed = Signal()

        self.comb += [
            proceed.eq(reduce(and_, [bc.round_accepting == next_round for bc in self.bc])),
            If(network_round < config.addresslayout.num_channels - 1,
                next_round.eq(network_round + 1)
            ).Else(
                next_round.eq(0)
            )
        ]

        self.sync += If(proceed,
            network_round.eq(next_round)
        )

        self.comb += [
            self.srr.current_round.eq(network_round),
            self.ext_srr.current_round.eq(network_round)
        ]

        # detect end of computation
        self.inactive = Signal()
        self.comb += self.inactive.eq(reduce(and_, computation_end))
