from migen import *

from migen.genlib.roundrobin import *

from functools import reduce
from operator import and_
import logging
import math

from util.recordfifo import *
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
        logger = logging.getLogger("sim.arbiter" + str(self.pe_id))
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
                        logger.warning("{}: received message's parity ({}) does not match current round ({})".format(num_cycles, (yield self.apply_interface_out.msg.roundpar), (level-1) % tb.config.addresslayout.num_channels))
            yield

class Router(Module):
    def __init__(self, config, fpga_id):
        self.dest_pe_in = Signal(config.addresslayout.peidsize)
        self.fpga_out = Signal(max=config.addresslayout.num_fpga)


        stmt = If(self.dest_pe_in < config.addresslayout.num_pe_per_fpga, self.fpga_out.eq(0))
        i = 1
        while i < config.addresslayout.num_fpga - 1:
            stmt = stmt.Elif(self.dest_pe_in < (i+1)*config.addresslayout.num_pe_per_fpga, self.fpga_out.eq(i))
            i += 1
        if config.addresslayout.num_fpga > 1:
            stmt = stmt.Else(self.fpga_out.eq(config.addresslayout.num_fpga - 1))

        self.comb += stmt
        # self.comb += [If((self.dest_pe_in >= i*config.addresslayout.num_pe_per_fpga) & (self.dest_pe_in < (i+1)*config.addresslayout.num_pe_per_fpga), self.fpga_out.eq(i)) for i in range(config.addresslayout.num_fpga)]


def rconnect(self, other, keep=None, omit=None):
    if keep is None:
        _keep = set([f[0] for f in self.layout])
    elif isinstance(keep, list):
        _keep = set(keep)
    else:
        _keep = keep
    if omit is None:
        _omit = set()
    elif isinstance(omit, list):
        _omit = set(omit)
    else:
        _omit = omit

    _keep = _keep - _omit

    r = []
    for f in self.layout:
        field = f[0]
        self_e = getattr(self, field)
        if isinstance(self_e, Signal):
            if field in _keep:
                direction = f[2]
                if direction == DIR_S_TO_M:
                    r.append(getattr(other, field).eq(self_e))
                elif direction == DIR_M_TO_S:
                    r.append(self_e.eq(getattr(other, field)))
                else:
                    raise TypeError
        else:
            r += rconnect(self_e, getattr(other, field), keep=keep, omit=omit)
    return r

class MuxTree(Module):
    def __init__(self, config, in_array, round_attr="msg.roundpar", fifo_depth=2):
        if len(in_array) == 0:
            raise ValueError("in_array should not be empty")

        mux_factor = 6
        self.submodules.fifo = InterfaceFIFO(layout=in_array[0].layout, depth=fifo_depth)
        self.current_round = Signal(config.addresslayout.channel_bits)

        if len(in_array) == 1:
            self.comb += [
                in_array[0].connect(self.fifo.din)
            ]
            self.interface_out = self.fifo.dout

        elif len(in_array) <= mux_factor:
            self.submodules.roundrobin = RoundRobin(len(in_array), switch_policy=SP_CE)

            # arrays for choosing incoming fifo to use
            if not isinstance(in_array, Array):
                in_array = Array(in_array)

            chosen = in_array[self.roundrobin.grant]

            self.comb += [
                rconnect(self.fifo.din, chosen, omit={'valid', 'ack'}),
                self.fifo.din.valid.eq(chosen.valid & (reduce(getattr, round_attr.split('.'), chosen) == self.current_round)),
                chosen.ack.eq(self.fifo.din.ack & (reduce(getattr, round_attr.split('.'), chosen) == self.current_round)),
                [self.roundrobin.request[i].eq(in_array[i].valid & (reduce(getattr, round_attr.split('.'), in_array[i]) == self.current_round)) for i in range(len(in_array))],
                self.roundrobin.ce.eq(1),
            ]

            self.interface_out = self.fifo.dout

        else:
            subgroup_length = math.ceil(len(in_array)/mux_factor)
            num_submuxes = math.ceil(len(in_array)/subgroup_length)
            self.submodules.submux = [MuxTree(config, in_array[i*subgroup_length:min(len(in_array), (i+1)*subgroup_length)], fifo_depth=fifo_depth) for i in range(num_submuxes)]
            self.submodules.mux = MuxTree(config, [self.submux[i].interface_out for i in range(num_submuxes)], fifo_depth=fifo_depth)
            self.comb += [
                [self.submux[i].current_round.eq(self.current_round) for i in range(num_submuxes)],
                self.mux.current_round.eq(self.current_round)
            ]

            self.interface_out = self.mux.interface_out

class SimpleRoundrobin(Module):
    def __init__(self, config, in_array, out_record):
        self.current_round = Signal(config.addresslayout.channel_bits)

        if len(in_array) == 1:
            self.comb += in_array[0].connect(out_record)
        else:
            self.submodules.roundrobin = RoundRobin(len(in_array), switch_policy=SP_CE)
            # arrays for choosing incoming fifo to use
            if not isinstance(in_array, Array):
                in_array = Array(in_array)
            # array_ack = Array(interface.ack for interface in in_array)
            # array_valid = Array(interface.valid for interface in in_array)
            # array_round = Array(interface.msg.roundpar for interface in in_array)

            for field in out_record.layout:
                if field[0] == "valid" or field[0] == "ack":
                    continue
                if len(field) == 3 and field[2] == DIR_S_TO_M:
                    self.comb += [getattr(i, field).eq(getattr(out_record, field)) for i in in_array]
                else:
                    self.comb += getattr(out_record, field[0]).eq(getattr(in_array[self.roundrobin.grant], field[0]))

            self.comb += [
                out_record.valid.eq(in_array[self.roundrobin.grant].valid & (in_array[self.roundrobin.grant].msg.roundpar == self.current_round)),
                in_array[self.roundrobin.grant].ack.eq(out_record.ack & (in_array[self.roundrobin.grant].msg.roundpar == self.current_round)),
                [self.roundrobin.request[i].eq(a.valid & (a.msg.roundpar == self.current_round)) for i, a in enumerate(in_array)],
                self.roundrobin.ce.eq(1)
            ]

class Network(Module):
    def __init__(self, config, fifo_depth=2):
        num_pe = config.addresslayout.num_pe

        self.apply_interface = [ApplyInterface(name="network_out", **config.addresslayout.get_params()) for _ in range(num_pe)]
        self.network_interface = [NetworkInterface(name="network_in", **config.addresslayout.get_params()) for _ in range(num_pe)]

        fifos = [[InterfaceFIFO(layout=self.apply_interface[0].layout, depth=fifo_depth) for i in range(num_pe)] for j in range(num_pe)]

        self.submodules.fifos = fifos

        self.submodules.arbiter = [Arbiter(sink, config) for sink in range(num_pe)]

        self.submodules.muxtree = [SimpleRoundrobin(config, [fifos[sink][source].dout for source in range(num_pe)], self.arbiter[sink].apply_interface_in) for sink in range(num_pe)]

        # connect PE incoming ports
        for sink in range(num_pe):
            self.comb += [
                self.muxtree[sink].current_round.eq(self.arbiter[sink].current_round),
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

class MultiNetwork(Module):
    def __init__(self, config, fpga_id, fifo_depth=2):
        self.config = config
        start_pe = fpga_id*config.addresslayout.num_pe_per_fpga
        num_local_pe = min(config.addresslayout.num_pe_per_fpga, config.addresslayout.num_pe - start_pe) #TODO: test non-equally distributed amount of PEs
        num_fpga = config.addresslayout.num_fpga


        self.apply_interface = [ApplyInterface(name="network_out", **config.addresslayout.get_params()) for _ in range(num_local_pe)]
        self.network_interface = [NetworkInterface(name="network_in", **config.addresslayout.get_params()) for _ in range(num_local_pe)]

        self.external_network_interface_in = [NetworkInterface(name="ext_network_in", **config.addresslayout.get_params()) for _ in range(num_fpga - 1)]
        self.external_network_interface_out = [NetworkInterface(name="ext_network_out", **config.addresslayout.get_params()) for _ in range(num_fpga - 1)]

        self.submodules.arbiter = [Arbiter(sink, config) for sink in range(num_local_pe)]

        self.submodules.per_fpga_fifos = [[InterfaceFIFO(layout=self.network_interface[0].layout, depth=fifo_depth, name="ext_link_{}_{}".format(start_pe+source, sink)) for sink in range(num_fpga)] for source in range(num_local_pe)]

        self.submodules.fifos = [[InterfaceFIFO(layout=self.network_interface[0].layout, depth=fifo_depth, name="link_{}_{}".format(start_pe+source, start_pe+sink)) for sink in range(num_local_pe)] for source in range(num_local_pe + num_fpga - 1)]

        # Synchronization
        # After the local PEs all switch to the next round, the last messages
        # they sent to remote might still be hanging around in the various fifos.
        # Have to make sure they have left the FPGA before switching rounds.
        # Messages are in-order in the fifos so we can just count the number of
        # barriers sent and be sure the messages have passed too.
        network_round = Signal(config.addresslayout.channel_bits)
        self.local_network_round = network_round
        next_round = Signal(config.addresslayout.channel_bits)
        proceed = Signal()

        num_barriers_to_ext = [Signal(max=config.addresslayout.num_pe*config.addresslayout.num_pe_per_fpga) for _ in range(num_fpga - 1)]

        for i, ext in enumerate(self.external_network_interface_out):
            self.sync += [
                If(proceed,
                    num_barriers_to_ext[i].eq(0)
                ).Elif(ext.valid & ext.ack & ext.msg.barrier,
                    num_barriers_to_ext[i].eq(num_barriers_to_ext[i] + 1)
                )
            ]

        self.comb += [
            proceed.eq(sum(num_barriers_to_ext) == (config.addresslayout.num_pe - num_local_pe) * num_local_pe),
            If(network_round < config.addresslayout.num_channels - 1,
                next_round.eq(network_round + 1)
            ).Else(
                next_round.eq(0)
            )
        ]

        self.sync += If(proceed,
            network_round.eq(next_round)
        )

        # connect PE incoming ports

        self.submodules.muxtree = [MuxTree(config, [self.fifos[source][sink].dout for source in range(num_local_pe + num_fpga - 1)], fifo_depth=fifo_depth) for sink in range(num_local_pe)]

        for sink in range(num_local_pe):
            self.comb += [
                self.muxtree[sink].interface_out.connect(self.arbiter[sink].apply_interface_in, omit={'dest_pe', 'broadcast'}),
                self.muxtree[sink].current_round.eq(self.arbiter[sink].current_round),
                self.arbiter[sink].apply_interface_out.connect(self.apply_interface[sink])
            ]

        # connect PE outgoing ports

        # first sort by destination FPGA
        for source in range(num_local_pe):
            router = Router(config, fpga_id)
            self.submodules += router
            array = Array(self.per_fpga_fifos[source])
            self.comb += [self.network_interface[source].connect(fifo.din, omit={'valid', 'ack'}) for fifo in self.per_fpga_fifos[source]]

            self.comb += [
                router.dest_pe_in.eq(self.network_interface[source].dest_pe),
                array[router.fpga_out].din.valid.eq(self.network_interface[source].valid),
                self.network_interface[source].ack.eq(array[router.fpga_out].din.ack)
            ]

        # connect non-local destinations to external interfaces
        for i in range(num_fpga):
            if i == fpga_id:
                continue
            if i < fpga_id:
                out_i = i
            else:
                out_i = i-1
            srr = SimpleRoundrobin(config, [self.per_fpga_fifos[source][i].dout for source in range(num_local_pe)], self.external_network_interface_out[out_i])
            self.submodules += srr
            self.comb += [
                srr.current_round.eq(network_round)
            ]

        # distribute to local destinations
        for source in range(num_local_pe):
            source_fifos = Array(self.fifos[source][sink] for sink in range(num_local_pe))
            dest_pe = self.per_fpga_fifos[source][fpga_id].dout.dest_pe

            for sink in range(num_local_pe):
                self.comb += self.per_fpga_fifos[source][fpga_id].dout.connect(self.fifos[source][sink].din, omit={'valid', 'ack'})

            self.comb += [
                source_fifos[dest_pe - start_pe].din.valid.eq(self.per_fpga_fifos[source][fpga_id].dout.valid),
                self.per_fpga_fifos[source][fpga_id].dout.ack.eq(source_fifos[dest_pe - start_pe].din.ack)
            ]

        # distribute from external
        for ext_source in range(num_fpga - 1):
            ext_fifo = Array(self.fifos[num_local_pe + ext_source])
            ext = self.external_network_interface_in[ext_source]

            self.comb += [ ext.connect(ext_fifo[sink].din, omit={'valid', 'ack'}) for sink in range(num_local_pe) ]

            self.comb += [
                ext_fifo[ext.dest_pe - start_pe].din.valid.eq(ext.valid),
                ext.ack.eq(ext_fifo[ext.dest_pe - start_pe].din.ack)
            ]
