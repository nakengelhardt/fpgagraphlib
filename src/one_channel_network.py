from migen import *

from migen.genlib.roundrobin import *

from functools import reduce
from operator import and_
import logging
import math

from recordfifo import *
from core_interfaces import *
from core_barriercounter import Barriercounter

class Arbiter(Module):
    def __init__(self, pe_id, config):
        addresslayout = config.addresslayout
        nodeidsize = addresslayout.nodeidsize
        num_pe = addresslayout.num_pe
        self.pe_id = pe_id

        # input
        self.apply_interface_in = ApplyInterface(name="arbiter_in", **addresslayout.get_params())

        # output
        self.apply_interface_out = ApplyInterface(name="arbiter_out", **addresslayout.get_params())

        # input override for injecting the message starting the computation
        self.start_message = ApplyInterface(name="start_message", **addresslayout.get_params())
        self.start_message.select = Signal()

        self.submodules.barriercounter = Barriercounter(config)
        self.current_round = Signal(config.addresslayout.channel_bits)

        self.comb += [
            self.apply_interface_in.connect(self.barriercounter.apply_interface_in),
            self.current_round.eq(self.barriercounter.round_accepting)
        ]

        # choose between init and regular message channel
        self.comb += \
            If(self.start_message.select,
                self.start_message.connect(self.apply_interface_out)
            ).Else(
                self.barriercounter.apply_interface_out.connect(self.apply_interface_out)
            )
    def gen_selfcheck(self, tb):
        logger = logging.getLogger("simulation.arbiter" + str(self.pe_id))
        level = 0
        num_cycles = 0

        while not (yield tb.global_inactive):
            num_cycles += 1

            if (yield self.apply_interface_out.valid) and (yield self.apply_interface_out.ack):
                if (yield self.apply_interface_out.msg.barrier):
                    level += 1
                    logger.debug("{}: Barrier passed to apply".format(num_cycles))
                else:
                    if (level-1) % tb.config.addresslayout.num_channels != (yield self.apply_interface_out.msg.roundpar):
                        logger.warning("{}: received message's parity ({}) does not match current round ({})".format(num_cycles, (yield self.apply_interface_out.msg.roundpar), level))
            yield

class MuxTree(Module):
    def __init__(self, config, in_array):
        mux_factor = 6
        self.apply_interface_out = ApplyInterface(name="mux_apply_interface_out", **config.addresslayout.get_params())
        self.current_round = Signal(config.addresslayout.channel_bits)

        if len(in_array) == 0:
            raise ValueError("in_array should not be empty")

        if len(in_array) == 1:
            self.submodules.fifo = RecordFIFO(layout=self.apply_interface_out.msg.layout, depth=2)
            self.comb += [
                in_array[0].msg.connect(self.fifo.din),
                self.fifo.we.eq(in_array[0].valid),
                in_array[0].ack.eq(self.fifo.writable),
                self.fifo.dout.connect(self.apply_interface_out.msg),
                self.apply_interface_out.valid.eq(self.fifo.readable),
                self.fifo.re.eq(self.apply_interface_out.ack)
            ]

        elif len(in_array) <= mux_factor:
            self.submodules.fifo = RecordFIFO(layout=self.apply_interface_out.msg.layout, depth=2)
            self.submodules.roundrobin = RoundRobin(len(in_array), switch_policy=SP_CE)

            # arrays for choosing incoming fifo to use
            array_data = Array(interface.msg.raw_bits() for interface in in_array)
            array_re = Array(interface.ack for interface in in_array)
            array_readable = Array(interface.valid for interface in in_array)
            array_round = Array(interface.msg.roundpar for interface in in_array)

            self.comb += [
                self.fifo.din.raw_bits().eq(array_data[self.roundrobin.grant]),
                self.fifo.we.eq(array_readable[self.roundrobin.grant] & (array_round[self.roundrobin.grant] == self.current_round)),
                array_re[self.roundrobin.grant].eq(self.fifo.writable & (array_round[self.roundrobin.grant] == self.current_round)),
                [self.roundrobin.request[i].eq(array_readable[i] & (array_round[i] == self.current_round)) for i in range(len(in_array))],
                self.roundrobin.ce.eq(self.fifo.writable | ~self.fifo.we),
                self.fifo.dout.connect(self.apply_interface_out.msg),
                self.apply_interface_out.valid.eq(self.fifo.readable),
                self.fifo.re.eq(self.apply_interface_out.ack)
            ]

        else:
            subgroup_length = math.ceil(len(in_array)/mux_factor)
            num_submuxes = math.ceil(len(in_array)/subgroup_length)
            self.submodules.submux = [MuxTree(config, in_array[i*subgroup_length:min(len(in_array), (i+1)*subgroup_length)]) for i in range(num_submuxes)]
            self.submodules.mux = MuxTree(config, [self.submux[i].apply_interface_out for i in range(num_submuxes)])
            self.comb += [
                [self.submux[i].current_round.eq(self.current_round) for i in range(num_submuxes)],
                self.mux.current_round.eq(self.current_round),
                self.mux.apply_interface_out.connect(self.apply_interface_out)
            ]

class Router(Module):
    def __init__(self, config, pe_start, pe_end):
        self.dest_pe_in = Signal(config.addresslayout.peidsize)
        self.sink_out = Signal(config.addresslayout.peidsize)

        self.comb += [
            If((self.dest_pe_in >= pe_start) & (self.dest_pe_in < pe_end),
                self.sink_out.eq(self.dest_pe_in - pe_start)
            ).Else(
                self.sink_out.eq(pe_end - pe_start)
            )
        ]


class Network(Module):
    def __init__(self, config, pe_start, pe_end):
        self.config = config
        num_local_pe = pe_end - pe_start
        num_pe = config.addresslayout.num_pe
        num_nodes_per_pe = config.addresslayout.num_nodes_per_pe

        self.apply_interface = [ApplyInterface(name="network_out", **config.addresslayout.get_params()) for _ in range(num_local_pe)]
        self.network_interface = [NetworkInterface(name="network_in", **config.addresslayout.get_params()) for _ in range(num_local_pe)]

        self.external_network_interface_in = NetworkInterface(name="ext_network_in", **config.addresslayout.get_params())
        self.external_network_interface_out = NetworkInterface(name="ext_network_out", **config.addresslayout.get_params())
        self.ext_network_current_round = Signal(config.addresslayout.channel_bits)
        self.local_network_round = Signal(config.addresslayout.channel_bits)

        fifos = [[InterfaceFIFOBuffered(layout=self.network_interface[0].layout, depth=8, name="link_{}_{}".format(sink, source)) for sink in range(num_local_pe + 1)] for source in range(num_local_pe + 1)]

        self.submodules.fifos = fifos

        self.submodules.arbiter = [Arbiter(sink, config) for sink in range(num_local_pe)]

        self.submodules.muxtree = [MuxTree(config, [fifos[sink][source].dout for source in range(num_local_pe + 1)]) for sink in range(num_local_pe)]
        # connect PE incoming ports
        for sink in range(num_local_pe):
            self.comb += [
                self.muxtree[sink].current_round.eq(self.arbiter[sink].current_round),
                self.muxtree[sink].apply_interface_out.connect(self.arbiter[sink].apply_interface_in),
                self.arbiter[sink].apply_interface_out.connect(self.apply_interface[sink])
            ]

        # connect PE outgoing ports
        for source in range(num_local_pe):
            array_msg = Array(fifo.din.msg.raw_bits() for fifo in [fifos[sink][source] for sink in range(num_local_pe + 1)])
            array_dest_pe = Array(fifo.din.dest_pe for fifo in [fifos[sink][source] for sink in range(num_local_pe + 1)])
            array_valid = Array(fifo.din.valid for fifo in [fifos[sink][source] for sink in range(num_local_pe + 1)])
            array_ack = Array(fifo.din.ack for fifo in [fifos[sink][source] for sink in range(num_local_pe + 1)])

            router = Router(config, pe_start, pe_end)
            self.submodules += router

            self.comb += [
                router.dest_pe_in.eq(self.network_interface[source].dest_pe),
                array_msg[router.sink_out].eq(self.network_interface[source].msg.raw_bits()),
                array_dest_pe[router.sink_out].eq(self.network_interface[source].dest_pe),
                array_valid[router.sink_out].eq(self.network_interface[source].valid),
                self.network_interface[source].ack.eq(array_ack[router.sink_out])
            ]

        # connect external interface

        # pull from outside
        network_round = Signal(config.addresslayout.channel_bits)
        next_round = Signal(config.addresslayout.channel_bits)
        proceed = Signal()

        self.comb += [
            proceed.eq(reduce(and_, [a.current_round == next_round for a in self.arbiter])),
            If(network_round < config.addresslayout.num_channels - 1,
                next_round.eq(network_round + 1)
            ).Else(
                next_round.eq(0)
            ),
            self.local_network_round.eq(network_round)
        ]

        self.sync += If(proceed,
            network_round.eq(next_round)
        )

        fifo_msg_in = Array(fifo.din.msg.raw_bits() for fifo in [fifos[sink][num_local_pe] for sink in range(num_local_pe + 1)])
        fifo_dest_pe_in = Array(fifo.din.dest_pe for fifo in [fifos[sink][num_local_pe] for sink in range(num_local_pe + 1)])
        fifo_valid_in = Array(fifo.din.valid for fifo in [fifos[sink][num_local_pe] for sink in range(num_local_pe + 1)])
        fifo_ack_in = Array(fifo.din.ack for fifo in [fifos[sink][num_local_pe] for sink in range(num_local_pe + 1)])
        fifo_round_in = Array(fifo.din.msg.roundpar for fifo in [fifos[sink][num_local_pe] for sink in range(num_local_pe + 1)])

        router = Router(config, pe_start, pe_end)
        self.submodules += router

        self.comb += [
            router.dest_pe_in.eq(self.external_network_interface_in.dest_pe),
            fifo_msg_in[router.sink_out].eq(self.external_network_interface_in.msg.raw_bits()),
            fifo_dest_pe_in[router.sink_out].eq(self.external_network_interface_in.dest_pe),
            fifo_valid_in[router.sink_out].eq(self.external_network_interface_in.valid & (self.external_network_interface_in.msg.roundpar == self.local_network_round)),
            self.external_network_interface_in.ack.eq(fifo_ack_in[router.sink_out] & (self.external_network_interface_in.msg.roundpar == self.local_network_round))
        ]

        # push to outside
        fifo_msg_out = Array(fifo.dout.msg.raw_bits() for fifo in [fifos[num_local_pe][source] for source in range(num_local_pe + 1)])
        fifo_dest_pe_out = Array(fifo.dout.dest_pe for fifo in [fifos[num_local_pe][source] for source in range(num_local_pe + 1)])
        fifo_round_out = Array(fifo.dout.msg.roundpar for fifo in [fifos[num_local_pe][source] for source in range(num_local_pe + 1)])
        fifo_valid_out = Array(fifo.dout.valid for fifo in [fifos[num_local_pe][source] for source in range(num_local_pe + 1)])
        fifo_ack_out = Array(fifo.dout.ack for fifo in [fifos[num_local_pe][source] for source in range(num_local_pe + 1)])

        self.submodules.roundrobin = RoundRobin(num_local_pe + 1, switch_policy=SP_CE)
        roundpar = Signal(config.addresslayout.channel_bits)

        self.comb += [
            [self.roundrobin.request[i].eq(fifo_valid_out[i] & (fifo_round_out[i] == self.ext_network_current_round)) for i in range(num_local_pe + 1)],
            self.roundrobin.ce.eq(1),
            self.external_network_interface_out.msg.raw_bits().eq(fifo_msg_out[self.roundrobin.grant]),
            self.external_network_interface_out.dest_pe.eq(fifo_dest_pe_out[self.roundrobin.grant]),
            self.external_network_interface_out.valid.eq(fifo_valid_out[self.roundrobin.grant] & (fifo_round_out[self.roundrobin.grant] == self.ext_network_current_round)),
            fifo_ack_out[self.roundrobin.grant].eq(self.external_network_interface_out.ack & (fifo_round_out[self.roundrobin.grant] == self.ext_network_current_round))
        ]
