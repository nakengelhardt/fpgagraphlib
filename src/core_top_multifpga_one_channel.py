from migen.fhdl import verilog
from migen import *
from migen.genlib.roundrobin import *
from migen.genlib.cdc import *
from tbsupport import *

from functools import reduce
from operator import and_

import logging
import random

from core_init import init_parse

from recordfifo import *
from core_interfaces import Message
from one_channel_network import Network
from core_apply import Apply
from core_scatter import Scatter

class Core(Module):
    def __init__(self, config, pe_start, pe_end):
        self.config = config
        self.pe_start = pe_start

        num_local_pe = pe_end - pe_start
        num_pe = self.config.addresslayout.num_pe
        num_nodes_per_pe = self.config.addresslayout.num_nodes_per_pe

        num_nodes = len(config.adj_dict)

        if config.has_edgedata:
            init_edgedata = config.init_edgedata[pe_start:pe_end]
        else:
            init_edgedata = [None for _ in range(num_local_pe)]

        self.submodules.network = Network(config, pe_start, pe_end)
        self.submodules.apply = [Apply(config, i, config.init_nodedata[i] if config.init_nodedata else None) for i in range(pe_start, pe_end)]

        self.submodules.scatter = [Scatter(i, config, adj_mat=(config.adj_idx[i], config.adj_val[i]), edge_data=init_edgedata[i-pe_start]) for i in range(pe_start, pe_end)]

        # connect within PEs
        self.comb += [self.apply[i].scatter_interface.connect(self.scatter[i].scatter_interface) for i in range(num_local_pe)]

        # connect to network
        self.comb += [self.network.apply_interface[i].connect(self.apply[i].apply_interface) for i in range(num_local_pe)]
        self.comb += [self.scatter[i].network_interface.connect(self.network.network_interface[i]) for i in range(num_local_pe)]

        # state of calculation
        self.global_inactive = Signal()
        self.comb += self.global_inactive.eq(reduce(and_, [pe.inactive for pe in self.apply]))

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

        network_round = Signal(config.addresslayout.channel_bits)
        next_round = Signal(config.addresslayout.channel_bits)
        proceed = Signal()

        self.comb += [
            proceed.eq(reduce(and_, [core.network.local_network_round == next_round for core in self.cores])),
            If(network_round < config.addresslayout.num_channels - 1,
                next_round.eq(network_round + 1)
            ).Else(
                next_round.eq(0)
            ),
            [core.network.ext_network_current_round.eq(network_round) for core in self.cores]
        ]

        self.sync += If(proceed,
            network_round.eq(next_round)
        )

        ext_msg_channel_out = Array(core.network.external_network_interface_out.msg.raw_bits() for core in self.cores)
        ext_dest_pe_channel_out = Array(core.network.external_network_interface_out.dest_pe for core in self.cores)
        ext_valid_channel_out = Array(core.network.external_network_interface_out.valid for core in self.cores)
        ext_ack_channel_out = Array(core.network.external_network_interface_out.ack for core in self.cores)

        fifos = [InterfaceFIFOBuffered(layout=self.cores[0].network.external_network_interface_out.layout, depth=8, name="ext_link_to_{}".format(sink)) for sink in range(config.addresslayout.num_fpga)]
        self.submodules += fifos

        for core in range(config.addresslayout.num_fpga):
            self.comb += fifos[core].dout.connect(self.cores[core].network.external_network_interface_in)

        ext_msg_channel_in = Array(fifos[core].din.msg.raw_bits() for core in range(config.addresslayout.num_fpga))
        ext_dest_pe_channel_in = Array(fifos[core].din.dest_pe for core in range(config.addresslayout.num_fpga))
        ext_valid_channel_in = Array(fifos[core].din.valid for core in range(config.addresslayout.num_fpga))
        ext_ack_channel_in = Array(fifos[core].din.ack for core in range(config.addresslayout.num_fpga))

        self.submodules.roundrobin = RoundRobin(config.addresslayout.num_fpga, switch_policy=SP_CE)

        self.submodules.adrlook = AddressLookup(config)

        self.comb += [
            [self.roundrobin.request[i].eq(ext_valid_channel_out[i]) for i in range(config.addresslayout.num_fpga)],
            self.roundrobin.ce.eq(1),
            self.adrlook.pe_adr_in.eq(ext_dest_pe_channel_out[self.roundrobin.grant]),
            ext_msg_channel_in[self.adrlook.fpga_out].eq(ext_msg_channel_out[self.roundrobin.grant]),
            ext_dest_pe_channel_in[self.adrlook.fpga_out].eq(ext_dest_pe_channel_out[self.roundrobin.grant]),
            ext_valid_channel_in[self.adrlook.fpga_out].eq(ext_valid_channel_out[self.roundrobin.grant]),
            ext_ack_channel_out[self.roundrobin.grant].eq(ext_ack_channel_in[self.adrlook.fpga_out])
        ]

        start_message = [a.start_message for core in self.cores for a in core.network.arbiter]
        layout = Message(**config.addresslayout.get_params()).layout
        initdata = [[convert_record_to_int(layout, barrier=0, roundpar=config.addresslayout.num_channels-1, dest_id=msg['dest_id'], sender=msg['sender'], payload=msg['payload'], halt=0) for msg in init_message] for init_message in config.init_messages]
        for i in initdata:
            i.append(convert_record_to_int(layout, barrier=1, roundpar=config.addresslayout.num_channels-1))
        initfifos = [RecordFIFO(layout=layout, depth=len(ini)+1, init=ini) for ini in initdata]

        for i in range(config.addresslayout.num_pe):
            initfifos[i].readable.name_override = "initfifos{}_readable".format(i)
            initfifos[i].re.name_override = "initfifos{}_re".format(i)
            initfifos[i].dout.name_override = "initfifos{}_dout".format(i)

        self.submodules += initfifos

        self.start = Signal()
        init = Signal()
        self.done = Signal()
        self.cycle_count = Signal(32)

        self.sync += [
            init.eq(self.start & reduce(or_, [i.readable for i in initfifos]))
        ]

        self.comb += [
            self.done.eq(~init & self.global_inactive)
        ]

        for i in range(config.addresslayout.num_pe):
            self.comb += [
                start_message[i].select.eq(init),
                start_message[i].msg.eq(initfifos[i].dout),
                start_message[i].valid.eq(initfifos[i].readable),
                initfifos[i].re.eq(start_message[i].ack)
            ]

        self.sync += [
            If(reduce(or_, [i.readable for i in initfifos]),
                self.cycle_count.eq(0)
            ).Elif(~self.global_inactive,
                self.cycle_count.eq(self.cycle_count + 1)
            )
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

def export(config, filename='top.v'):

    m = UnCore(config)

    verilog.convert(m,
                    name="top",
                    ios={m.start, m.done, m.cycle_count}
                    ).write(filename)

def main():
    args, config = init_parse()

    logger = logging.getLogger('config')

    if args.command=='sim':
        logger.info("Starting Simulation")
        sim(config)
    if args.command=='export':
        filename = "top.v"
        if args.output:
            filename = args.output
        logger.info("Exporting design to file {}".format(filename))
        export(config, filename=filename)

if __name__ == '__main__':
    main()
