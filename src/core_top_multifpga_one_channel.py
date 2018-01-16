from migen.fhdl import verilog
from migen import *
from migen.genlib.roundrobin import *
from migen.genlib.cdc import *
from migen.genlib.coding import PriorityEncoder
from tbsupport import *

from functools import reduce
from operator import and_, or_

import logging
import random
import os

from core_init import init_parse

from recordfifo import *
from core_interfaces import Message
from one_channel_network import Network
from core_apply import Apply
from core_scatter import Scatter
from core_ddr import DDRPortSharer

class Core(Module):
    def __init__(self, config, pe_start, pe_end):
        self.config = config
        self.pe_start = pe_start

        num_local_pe = pe_end - pe_start
        num_pe = self.config.addresslayout.num_pe
        num_nodes_per_pe = self.config.addresslayout.num_nodes_per_pe

        num_nodes = len(config.adj_dict)

        if config.has_edgedata:
            assert not config.use_ddr
            init_edgedata = config.init_edgedata[pe_start:pe_end]
        else:
            init_edgedata = [None for _ in range(num_local_pe)]

        if config.use_ddr:
            self.submodules.portsharer = DDRPortSharer(config=config, num_ports=num_local_pe)

        self.submodules.network = Network(config, pe_start, pe_end)
        self.submodules.apply = [Apply(config, i, config.init_nodedata[i] if config.init_nodedata else None) for i in range(pe_start, pe_end)]

        self.submodules.scatter = [Scatter(i, config, adj_mat=(config.adj_idx[i], config.adj_val[i]), edge_data=init_edgedata[i-pe_start], hmc_port=self.portsharer.get_port(i-pe_start) if config.use_ddr else None) for i in range(pe_start, pe_end)]

        # connect within PEs
        self.comb += [self.apply[i].scatter_interface.connect(self.scatter[i].scatter_interface) for i in range(num_local_pe)]

        # connect to network
        self.comb += [self.network.apply_interface[i].connect(self.apply[i].apply_interface) for i in range(num_local_pe)]
        self.comb += [self.scatter[i].network_interface.connect(self.network.network_interface[i]) for i in range(num_local_pe)]

        # state of calculation
        self.global_inactive = Signal()
        self.comb += self.global_inactive.eq(reduce(and_, [pe.inactive for pe in self.apply]))

        start_message = [a.start_message for a in self.network.arbiter]
        layout = Message(**config.addresslayout.get_params()).layout
        initdata = []
        for i in range(pe_start, pe_end):
            initdata.append([convert_record_to_int(layout, barrier=0, roundpar=config.addresslayout.num_channels-1, dest_id=msg['dest_id'], sender=msg['sender'], payload=msg['payload'], halt=0) for msg in config.init_messages[i]])
        for i in initdata:
            i.append(convert_record_to_int(layout, barrier=1, roundpar=config.addresslayout.num_channels-1))
        initfifos = [RecordFIFO(layout=layout, depth=len(ini)+1, init=ini, name="initfifo_"+str(i)) for i, ini in enumerate(initdata)]

        self.submodules += initfifos

        self.start = Signal()
        init = Signal()
        self.done = Signal()
        self.cycle_count = Signal(64)

        self.sync += [
            init.eq(self.start & reduce(or_, [i.readable for i in initfifos]))
        ]

        self.comb += [
            self.done.eq(~init & self.global_inactive)
        ]

        for i, initfifo in enumerate(initfifos):
            self.comb += [
                start_message[i].select.eq(init),
                start_message[i].msg.eq(initfifo.dout),
                start_message[i].valid.eq(initfifo.readable),
                initfifo.re.eq(start_message[i].ack)
            ]

        self.sync += [
            If(~self.start,
                self.cycle_count.eq(0)
            ).Elif(~self.global_inactive,
                self.cycle_count.eq(self.cycle_count + 1)
            )
        ]

        self.total_num_messages = Signal(32)
        self.comb += [
            self.total_num_messages.eq(sum(scatter.barrierdistributor.total_num_messages for scatter in self.scatter))
        ]

    def gen_barrier_monitor(self, tb):
        logger = logging.getLogger('simulation.barriermonitor')
        num_pe = self.config.addresslayout.num_pe
        num_local_pe = len(self.apply)

        num_cycles = 0
        while not (yield tb.global_inactive):
            num_cycles += 1
            for a in self.apply:
                if ((yield a.apply_interface.valid) and (yield a.apply_interface.ack)):
                    if (yield a.apply_interface.msg.barrier):
                        logger.debug(str(num_cycles) + ": Barrier enters Apply on PE " + str(a.pe_id))
                if (yield a.gatherkernel.valid_in) and (yield a.gatherkernel.ready):
                    if ((yield a.level) - 1) % self.config.addresslayout.num_channels != (yield a.roundpar):
                        logger.warning("{}: received message's parity ({}) does not match current round ({})".format(num_cycles, (yield a.roundpar), (yield a.level)))
                if ((yield a.scatter_interface.barrier) and (yield a.scatter_interface.valid) and (yield a.scatter_interface.ack)):
                    logger.debug(str(num_cycles) + ": Barrier exits Apply on PE " + str(a.pe_id))
            for s in self.scatter:
                if ((yield s.scatter_interface.valid) and (yield s.scatter_interface.ack)):
                    if (yield s.scatter_interface.barrier):
                        logger.debug(str(num_cycles) + ": Barrier enters Scatter on PE " + str(s.pe_id))
                if ((yield s.barrierdistributor.network_interface_in.valid) and (yield s.barrierdistributor.network_interface_in.ack)):
                    if (yield s.barrierdistributor.network_interface_in.msg.barrier):
                        logger.debug(str(num_cycles) + ": Barrier exits Scatter on PE " + str(s.pe_id))
            yield

class AddressLookup(Module):
    def __init__(self, config):
        self.pe_adr_in = Signal(config.addresslayout.peidsize)
        self.fpga_out = Signal(bits_for(config.addresslayout.num_fpga))

        adr = Array(i//config.addresslayout.num_pe_per_fpga for i in range(config.addresslayout.num_pe))

        self.comb += self.fpga_out.eq(adr[self.pe_adr_in])

class UnCore(Module):
    def __init__(self, config):
        self.config = config
        self.submodules.cores = [Core(config, i*config.addresslayout.num_pe_per_fpga, min((i+1)*config.addresslayout.num_pe_per_fpga, config.addresslayout.num_pe)) for i in range(config.addresslayout.num_fpga)]

        self.global_inactive = Signal()
        self.comb += self.global_inactive.eq(reduce(and_, [core.global_inactive for core in self.cores]))

        self.submodules.adrlook_sender = AddressLookup(config)
        broadcast = Signal()
        broadcast_port = Signal(max=max(2, config.addresslayout.num_ext_ports))
        got_ack = Signal(2*config.addresslayout.num_fpga)
        all_ack = Signal()

        self.submodules.fifo = [InterfaceFIFO(layout=self.cores[0].network.external_network_interface_out[port].layout, depth=8) for port in range(config.addresslayout.num_ext_ports)]

        for port in range(config.addresslayout.num_ext_ports):
            ext_msg_channel_out = Array(core.network.external_network_interface_out[port].msg.raw_bits() for core in self.cores)
            ext_dest_pe_channel_out = Array(core.network.external_network_interface_out[port].dest_pe for core in self.cores)
            ext_valid_channel_out = Array(core.network.external_network_interface_out[port].valid for core in self.cores)
            ext_ack_channel_out = Array(core.network.external_network_interface_out[port].ack for core in self.cores)
            ext_broadcast_channel_out = Array(core.network.external_network_interface_out[port].broadcast for core in self.cores)

            ext_ack_channel_in = Array(core.network.external_network_interface_in[port].ack for core in self.cores)

            roundrobin = RoundRobin(config.addresslayout.num_fpga, switch_policy=SP_CE)
            self.submodules += roundrobin

            adrlook = AddressLookup(config)
            self.submodules += adrlook

            self.comb += [
                [roundrobin.request[i].eq(ext_valid_channel_out[i]) for i in range(config.addresslayout.num_fpga)],
                roundrobin.ce.eq(1),
                self.fifo[port].din.msg.raw_bits().eq(ext_msg_channel_out[roundrobin.grant]),
                self.fifo[port].din.dest_pe.eq(ext_dest_pe_channel_out[roundrobin.grant]),
                self.fifo[port].din.broadcast.eq(ext_broadcast_channel_out[roundrobin.grant]),
                self.fifo[port].din.valid.eq(ext_valid_channel_out[roundrobin.grant]),
                ext_ack_channel_out[roundrobin.grant].eq(self.fifo[port].din.ack),
            ]

            self.comb += [
                adrlook.pe_adr_in.eq(self.fifo[port].dout.dest_pe),
                [core.network.external_network_interface_in[port].msg.raw_bits().eq(self.fifo[port].dout.msg.raw_bits()) for core in self.cores],
                [core.network.external_network_interface_in[port].dest_pe.eq(self.fifo[port].dout.dest_pe) for core in self.cores],
                [core.network.external_network_interface_in[port].broadcast.eq(broadcast) for core in self.cores],
                [self.cores[i].network.external_network_interface_in[port].valid.eq((~broadcast & self.fifo[port].dout.valid & (adrlook.fpga_out == i)) | (broadcast & ~((self.adrlook_sender.fpga_out == i) & (broadcast_port == port)) & ~got_ack[port*i])) for i in range(config.addresslayout.num_fpga)],
                self.fifo[port].dout.ack.eq((~broadcast & ext_ack_channel_in[adrlook.fpga_out]) | (broadcast & (port == broadcast_port) & all_ack))
            ]

        self.submodules.priorityencoder = PriorityEncoder(config.addresslayout.num_ext_ports)
        array_sender = Array(self.fifo[port].dout.msg.sender for port in range(config.addresslayout.num_ext_ports))

        self.comb += [self.priorityencoder.i[port].eq(self.fifo[port].dout.broadcast & self.fifo[port].dout.valid) for port in range(config.addresslayout.num_ext_ports)]

        self.comb += [
            self.adrlook_sender.pe_adr_in.eq(array_sender[broadcast_port]),
            broadcast.eq(~self.priorityencoder.n),
            broadcast_port.eq(self.priorityencoder.o)
        ]

        self.sync += [
            If(broadcast,
                If(all_ack,
                    got_ack.eq(0)
                ).Else(
                    [got_ack[port*i].eq(got_ack[port*i] | self.cores[i].network.external_network_interface_in[port].ack) for i in range(config.addresslayout.num_fpga) for port in range(config.addresslayout.num_ext_ports)]
                )
            )
        ]



        self.comb += [
            all_ack.eq(reduce(and_, [got_ack[port*i] | ((self.adrlook_sender.fpga_out == i) & (port == broadcast_port)) for i in range(config.addresslayout.num_fpga) for port in range(config.addresslayout.num_ext_ports)])),
        ]


        self.start = Signal()
        self.done = Signal()
        self.cycle_count = Signal(64)

        self.comb += [
            [core.start.eq(self.start) for core in self.cores],
            self.done.eq(reduce(and_, [core.done for core in self.cores])),
            self.cycle_count.eq(self.cores[0].cycle_count)
        ]

    def gen_simulation(self, tb):
        yield self.start.eq(1)

    def gen_network_stats(self):
        num_cycles = 0
        with open("{}.net_stats.{}pe.{}fpga.log".format(self.config.name, self.config.addresslayout.num_pe, self.config.addresslayout.num_fpga), 'w') as netstatsfile:
            netstatsfile.write("Cycle\tNumber of messages sent\n")
            while not (yield self.global_inactive):
                num_cycles += 1
                num_msgs = 0
                for core in self.cores:
                    for scatter in core.scatter:
                        if (yield scatter.network_interface.valid) and (yield scatter.network_interface.ack):
                            num_msgs += 1
                netstatsfile.write("{}\t{}\n".format(num_cycles, num_msgs))
                yield

def sim(config):
    tb = UnCore(config)

    generators = []

    for core in tb.cores:
        generators.extend([core.gen_barrier_monitor(tb)])

    generators.extend(get_simulators(tb, 'gen_selfcheck', tb))
    generators.extend(get_simulators(tb, 'gen_simulation', tb))

    run_simulation(tb, generators, vcd_name="tb.vcd")

def export_one(config, filename='top.v'):
    assert not config.use_ddr

    m = UnCore(config)

    verilog.convert(m,
                    name="top",
                    ios={m.start, m.done, m.cycle_count}
                    ).write(filename)

def export(config, filename='top'):

    m = [Core(config, i*config.addresslayout.num_pe_per_fpga, min((i+1)*config.addresslayout.num_pe_per_fpga, config.addresslayout.num_pe)) for i in range(config.addresslayout.num_fpga)]

    for i in range(config.addresslayout.num_fpga):
        iname = filename + "_" + str(i)
        os.makedirs(iname, exist_ok=True)
        with cd(iname):
            ios={m[i].start, m[i].done, m[i].cycle_count, m[i].total_num_messages}

            if config.use_ddr:
                ios |= m[i].portsharer.get_ios()

            for j in range(config.addresslayout.num_ext_ports):
                ios |= set(m[i].network.external_network_interface_in[j].flatten())
                ios |= set(m[i].network.external_network_interface_out[j].flatten())

            # debug signals
            for a in m[i].network.arbiter:
                ios.add(a.barriercounter.all_messages_recvd)
                ios.add(a.barriercounter.all_barriers_recvd)
                # ios |= set(a.barriercounter.barrier_from_pe)
                # ios |= set(a.barriercounter.num_from_pe)
                # ios |= set(a.barriercounter.num_expected_from_pe)

            verilog.convert(m[i],
                            name="top",
                            ios=ios
                            ).write(iname + ".v")

    if config.use_ddr:
        with open("adj_val.data", 'wb') as f:
            for x in config.adj_val:
                f.write(struct.pack('=I', x))

def main():
    args, config = init_parse()

    logger = logging.getLogger('config')

    if args.command=='sim':
        logger.info("Starting Simulation")
        sim(config)
    if args.command=='export_one':
        filename = "top.v"
        if args.output:
            filename = args.output
        logger.info("Exporting design to file {}".format(filename))
        export_one(config, filename=filename)
    if args.command=='export':
        filename = "top"
        if args.output:
            filename = args.output
        logger.info("Exporting design to files {}_[0-{}].v".format(filename, config.addresslayout.num_fpga-1))
        export(config, filename=filename)

if __name__ == '__main__':
    main()
