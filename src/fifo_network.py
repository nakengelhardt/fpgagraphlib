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



class Network(Module):
    def __init__(self, config):
        num_pe = config.addresslayout.num_pe
        num_nodes_per_pe = config.addresslayout.num_nodes_per_pe

        self.apply_interface = [ApplyInterface(name="network_out", **config.addresslayout.get_params()) for _ in range(num_pe)]
        self.network_interface = [NetworkInterface(name="network_in", **config.addresslayout.get_params()) for _ in range(num_pe)]

        fifos = [[InterfaceFIFOBuffered(layout=self.network_interface[0].layout, depth=8) for i in range(num_pe)] for j in range(num_pe)]

        self.submodules.fifos = fifos

        self.submodules.arbiter = [Arbiter(sink, config) for sink in range(num_pe)]

        self.submodules.muxtree = [MuxTree(config, [fifos[sink][source].dout for source in range(num_pe)]) for sink in range(num_pe)]
        # connect PE incoming ports
        for sink in range(num_pe):
            self.comb += [
                self.muxtree[sink].current_round.eq(self.arbiter[sink].current_round),
                self.muxtree[sink].apply_interface_out.connect(self.arbiter[sink].apply_interface_in),
                self.arbiter[sink].apply_interface_out.connect(self.apply_interface[sink])
            ]

        # connect PE outgoing ports
        for source in range(num_pe):
            array_msg = Array(fifo.din.msg.raw_bits() for fifo in [fifos[sink][source] for sink in range(num_pe)])
            array_we = Array(fifo.din.valid for fifo in [fifos[sink][source] for sink in range(num_pe)])
            array_writable = Array(fifo.din.ack for fifo in [fifos[sink][source] for sink in range(num_pe)])
            sink = Signal(config.addresslayout.peidsize)


            self.comb += [
                sink.eq(self.network_interface[source].dest_pe),
                array_msg[sink].eq(self.network_interface[source].msg.raw_bits()),
                array_we[sink].eq(self.network_interface[source].valid),
                self.network_interface[source].ack.eq(array_writable[sink])
            ]
