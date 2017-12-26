from migen import *

from migen.genlib.roundrobin import *
from migen.genlib.coding import PriorityEncoder

from functools import reduce
from operator import and_
import logging
import math

from tbsupport import *
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
        self.comb += [
            If(self.start_message.select,
                self.start_message.connect(self.apply_interface_out)
            ).Else(
                self.barriercounter.apply_interface_out.connect(self.apply_interface_out)
            )
        ]

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

class NetworkRoundSync(Module):
    def __init__(self, config):
        self.send_barrier = Signal()
        self.send_barrier_ack = Signal()

        self.receive_barrier = Signal()
        self.receive_barrier_ack = Signal()

        self.local_proceed = Signal()
        self.network_round = Signal(config.addresslayout.channel_bits)

        num_fpga_barriers = Signal(bits_for(config.addresslayout.num_fpga))
        next_round = Signal(config.addresslayout.channel_bits)
        self.proceed = Signal()
        ready_for_proceed = Signal()

        self.comb += [
            self.receive_barrier_ack.eq(~self.proceed),
            self.proceed.eq((num_fpga_barriers == (config.addresslayout.num_fpga - 1)) & self.local_proceed & ready_for_proceed)
        ]

        self.sync += [
            If(self.receive_barrier & self.receive_barrier_ack,
                num_fpga_barriers.eq(num_fpga_barriers + 1)
            ),
            If(self.proceed,
                If(self.network_round < config.addresslayout.num_channels - 1,
                    self.network_round.eq(self.network_round + 1)
                ).Else(
                    self.network_round.eq(0)
                ),
                num_fpga_barriers.eq(0)
            )
        ]

        self.submodules.fsm = FSM()
        self.fsm.act("IDLE",
            If(self.local_proceed,
                NextState("SEND_BARRIERS")
            )
        )
        self.fsm.act("SEND_BARRIERS",
            self.send_barrier.eq(1),
            If(self.send_barrier_ack,
                NextState("WAIT_FOR_PROCEED")
            )
        )
        self.fsm.act("WAIT_FOR_PROCEED",
            ready_for_proceed.eq(1),
            If(self.proceed,
                NextState("IDLE")
            )
        )

class EncapsulateFPGABarrier(Module):
    def __init__(self, config, ext_message_width, num_local_pe):
        self.send_barrier = Signal()
        self.send_barrier_ack = Signal()

        self.receive_barrier = Signal()
        self.receive_barrier_ack = Signal()

        self.message_in_data_inside = [Signal(ext_message_width) for _ in range(config.addresslayout.num_ext_ports)]
        self.message_in_valid_inside = [Signal() for _ in range(config.addresslayout.num_ext_ports)]
        self.message_in_ack_inside = [Signal() for _ in range(config.addresslayout.num_ext_ports)]

        self.message_in_data = [Signal(ext_message_width) for _ in range(config.addresslayout.num_ext_ports)]
        self.message_in_valid = [Signal() for _ in range(config.addresslayout.num_ext_ports)]
        self.message_in_ack = [Signal() for _ in range(config.addresslayout.num_ext_ports)]

        self.message_out_data_inside = Signal(ext_message_width * num_local_pe)
        self.message_out_valid_inside = Signal(num_local_pe)
        self.message_out_ack_inside = Signal(num_local_pe)

        self.message_out_data = Signal(ext_message_width * num_local_pe)
        self.message_out_valid = Signal(num_local_pe)
        self.message_out_ack = Signal(num_local_pe)

        barrier_message = NetworkInterface(**config.addresslayout.get_params())
        self.comb += [
            barrier_message.broadcast.eq(1),
            barrier_message.valid.eq(1),
            barrier_message.ack.eq(1)
        ]

        self.comb += [
            If(self.send_barrier,
                self.message_out_data.eq(barrier_message.raw_bits()),
                self.message_out_valid.eq(1),
                self.send_barrier_ack.eq(self.message_out_ack[0])
            ).Else(
                self.message_out_data.eq(self.message_out_data_inside),
                self.message_out_valid.eq(self.message_out_valid_inside),
                self.message_out_ack_inside.eq(self.message_out_ack)
            )
        ]

        self.submodules.pe = PriorityEncoder(config.addresslayout.num_ext_ports)

        for port in range(config.addresslayout.num_ext_ports):
            self.comb += [
                self.pe.i[port].eq((self.message_in_data[port] == barrier_message.raw_bits()) & self.message_in_valid[port]),
                If(self.pe.i[port],
                    self.receive_barrier.eq((self.pe.o == port)),
                    self.message_in_ack[port].eq(self.receive_barrier_ack & (self.pe.o == port))
                ).Else(
                    self.message_in_data_inside[port].eq(self.message_in_data[port]),
                    self.message_in_valid_inside[port].eq(self.message_in_valid[port]),
                    self.message_in_ack[port].eq(self.message_in_ack_inside[port])
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

        def printendpoint(n):
            if n < num_local_pe:
                return str(pe_start + n)
            else:
                return "ext{}".format(n - num_local_pe)

        if not hasattr(config.addresslayout, "num_ext_ports"):
            config.addresslayout.num_ext_ports = 1

        fifos = [[InterfaceFIFO(layout=self.network_interface[0].layout, depth=8, name="link_{}_{}".format(printendpoint(source), printendpoint(sink))) for sink in range(num_local_pe + 1)] for source in range(num_local_pe + config.addresslayout.num_ext_ports)]

        self.submodules.fifos = fifos

        self.submodules.arbiter = [Arbiter(sink, config) for sink in range(num_local_pe)]

        network_round = Signal(config.addresslayout.channel_bits)

        self.submodules.nrs = NetworkRoundSync(config)

        self.comb += [
            network_round.eq(self.nrs.network_round),
            self.nrs.local_proceed.eq(reduce(and_, [self.arbiter[i].current_round != network_round for i in range(num_local_pe)]))
        ]

        # connect PE outgoing ports
        for source in range(num_local_pe):
            array_msg = Array(fifo.din.msg.raw_bits() for fifo in [fifos[source][sink] for sink in range(num_local_pe + 1)])
            array_dest_pe = Array(fifo.din.dest_pe for fifo in [fifos[source][sink] for sink in range(num_local_pe + 1)])
            array_valid = Array(fifo.din.valid for fifo in [fifos[source][sink] for sink in range(num_local_pe + 1)])
            array_ack = Array(fifo.din.ack for fifo in [fifos[source][sink] for sink in range(num_local_pe + 1)])

            router = Router(config, pe_start, pe_end)
            self.submodules += router

            self.comb += [
                router.dest_pe_in.eq(self.network_interface[source].dest_pe),
                array_msg[router.sink_out].eq(self.network_interface[source].msg.raw_bits()),
                array_dest_pe[router.sink_out].eq(self.network_interface[source].dest_pe),
                array_valid[router.sink_out].eq(self.network_interface[source].valid & (self.network_interface[source].msg.roundpar == network_round)),
                self.network_interface[source].ack.eq(array_ack[router.sink_out] & ( ~self.network_interface[source].valid | (self.network_interface[source].msg.roundpar == network_round)))
            ]

        #connect incoming ports to PE
        for sink in range(num_local_pe):
            self.submodules.roundrobin = RoundRobin(num_local_pe+config.addresslayout.num_ext_ports, switch_policy=SP_CE)

            # arrays for choosing incoming fifo to use
            array_msg = Array(fifo.dout.msg.raw_bits() for fifo in [fifos[source][sink] for source in range(num_local_pe + config.addresslayout.num_ext_ports)])
            array_valid = Array(fifo.dout.valid for fifo in [fifos[source][sink] for source in range(num_local_pe + config.addresslayout.num_ext_ports)])
            array_ack = Array(fifo.dout.ack for fifo in [fifos[source][sink] for source in range(num_local_pe + config.addresslayout.num_ext_ports)])

            self.comb += [
                [self.roundrobin.request[i].eq(array_valid[i]) for i in range(num_local_pe + config.addresslayout.num_ext_ports)],
                self.roundrobin.ce.eq(1),
                self.arbiter[sink].apply_interface_in.msg.raw_bits().eq(array_msg[self.roundrobin.grant]),
                self.arbiter[sink].apply_interface_in.valid.eq(array_valid[self.roundrobin.grant]),
                array_ack[self.roundrobin.grant].eq(self.arbiter[sink].apply_interface_in.ack),
                self.arbiter[sink].apply_interface_out.connect(self.apply_interface[sink])
            ]

        # outside ports
        self.ext_message_width = 128
        self.message_in_data = [Signal(self.ext_message_width) for _ in range(config.addresslayout.num_ext_ports)]
        self.message_in_valid = [Signal() for _ in range(config.addresslayout.num_ext_ports)]
        self.message_in_ack = [Signal() for _ in range(config.addresslayout.num_ext_ports)]

        for port in range(config.addresslayout.num_ext_ports):
            message_in = NetworkInterface(**config.addresslayout.get_params())
            self.comb += message_in.raw_bits().eq(self.message_in_data[port])

            fifo_msg_in = Array(fifo.din.msg.raw_bits() for fifo in [fifos[num_local_pe+port][sink] for sink in range(num_local_pe + 1)])
            fifo_dest_pe_in = Array(fifo.din.dest_pe for fifo in [fifos[num_local_pe+port][sink] for sink in range(num_local_pe + 1)])
            fifo_valid_in = Array(fifo.din.valid for fifo in [fifos[num_local_pe+port][sink] for sink in range(num_local_pe + 1)])
            fifo_ack_in = Array(fifo.din.ack for fifo in [fifos[num_local_pe+port][sink] for sink in range(num_local_pe + 1)])
            fifo_round_in = Array(fifo.din.msg.roundpar for fifo in [fifos[num_local_pe+port][sink] for sink in range(num_local_pe + 1)])

            router = Router(config, pe_start, pe_end)
            self.submodules += router

            self.comb += [
                router.dest_pe_in.eq(message_in.dest_pe),
                fifo_msg_in[router.sink_out].eq(message_in.msg.raw_bits()),
                fifo_dest_pe_in[router.sink_out].eq(message_in.dest_pe),
                fifo_valid_in[router.sink_out].eq(self.message_in_valid[port] & (message_in.msg.roundpar == network_round)),
                self.message_in_ack[port].eq(fifo_ack_in[router.sink_out] & (message_in.msg.roundpar == network_round))
            ]

        self.message_out_data = Signal(self.ext_message_width * num_local_pe)
        self.message_out_valid = Signal(num_local_pe)
        self.message_out_ack = Signal(num_local_pe)

        for source in range(num_local_pe):
            self.comb += [
                self.message_out_data[source*self.ext_message_width:(source+1)*self.ext_message_width].eq(fifos[source][num_local_pe].dout.raw_bits()),
                self.message_out_valid[source].eq(fifos[source][num_local_pe].dout.valid),
                fifos[source][num_local_pe].dout.ack.eq(self.message_out_ack[source])
            ]

        # inject/filter inter-FPGA messages
        self.submodules.efb = EncapsulateFPGABarrier(config, self.ext_message_width, num_local_pe)

        self.comb += [
            self.efb.send_barrier.eq(self.nrs.send_barrier),
            self.nrs.send_barrier_ack.eq(self.efb.send_barrier_ack),
            self.nrs.receive_barrier.eq(self.efb.receive_barrier),
            self.efb.receive_barrier_ack.eq(self.nrs.receive_barrier_ack),
        ]

        for port in range(config.addresslayout.num_ext_ports):
            self.comb += [
                self.message_in_data[port].eq(self.efb.message_in_data_inside[port]),
                self.message_in_valid[port].eq(self.efb.message_in_valid_inside[port]),
                self.efb.message_in_ack_inside[port].eq(self.message_in_ack[port])
            ]

        self.comb += [
            self.efb.message_out_data_inside.eq(self.message_out_data),
            self.efb.message_out_valid_inside.eq(self.message_out_valid),
            self.message_out_ack.eq(self.efb.message_out_ack_inside)
        ]

        #I/Os
        self.ios = set()

        for port in range(config.addresslayout.num_ext_ports):
            self.ios.add(self.efb.message_in_data[port])
            self.ios.add(self.efb.message_in_valid[port])
            self.ios.add(self.efb.message_in_ack[port])

        self.ios.add(self.efb.message_out_data)
        self.ios.add(self.efb.message_out_valid)
        self.ios.add(self.efb.message_out_ack)
