from migen import *
from tbsupport import *
from migen.fhdl import verilog
import migen.build.xilinx.common
from migen.genlib.resetsync import AsyncResetSynchronizer
from migen.genlib.cdc import *


from functools import reduce
from operator import or_

from pico import PicoPlatform

# import unittest
import random
import sys
import argparse
import logging

from recordfifo import RecordFIFO
from graph_input import read_graph
from graph_generate import generate_graph, export_graph
from core_core_tb import Core
from core_interfaces import Message

from pr.config import Config

class Top(Module):
    def __init__(self, config):
        self.config = config
        num_pe = config.addresslayout.num_pe

        self.clock_domains.cd_sys = ClockDomain()
        sys_clk, _, sys_rst, _ = config.platform.getHMCClkEtc()
        # extra_clk = config.platform.getExtraClk()
        self.comb += [ self.cd_sys.clk.eq(sys_clk), self.cd_sys.rst.eq(sys_rst) ]

        # self.clock_domains.cd_pcie = ClockDomain()
        # clk, rst = config.platform.getStreamClkRst()
        # self.comb += [ self.cd_pcie.clk.eq(clk), self.cd_pcie.rst.eq(rst) ]

        self.clock_domains.cd_pico = ClockDomain()
        bus_clk, bus_rst = config.platform.getBusClkRst()
        self.comb += [ self.cd_pico.clk.eq(bus_clk), self.cd_pico.rst.eq(bus_rst) ]

        self.submodules.core = Core(config)

        start_message = [self.core.network.arbiter[i].start_message for i in range(num_pe)]
        layout = Message(**config.addresslayout.get_params()).layout
        initdata = [[convert_record_tuple_to_int((0, 1, msg['dest_id'], msg['sender'], msg['payload']), layout) for msg in init_message] for init_message in config.init_messages]
        for i in initdata:
            i.append(convert_record_tuple_to_int((1, 1, 0, 0, 0), layout))
        initfifos = [RecordFIFO(layout=layout, depth=len(ini)+1, init=ini) for ini in initdata]

        for i in range(num_pe):
            initfifos[i].readable.name_override = "initfifos{}_readable".format(i)
            initfifos[i].re.name_override = "initfifos{}_re".format(i)
            initfifos[i].dout.name_override = "initfifos{}_dout".format(i)

        self.submodules += initfifos

        start = Signal()
        init = Signal()
        self.done = Signal()
        self.cycle_count = Signal(32)

        self.sync += [
            init.eq(start & reduce(or_, [i.readable for i in initfifos]))
        ]

        self.comb += [
            self.done.eq(~init & self.core.global_inactive)
        ]

        for i in range(num_pe):
            self.comb += [
                start_message[i].select.eq(init),
                start_message[i].msg.eq(initfifos[i].dout),
                start_message[i].valid.eq(initfifos[i].readable),
                initfifos[i].re.eq(start_message[i].ack)
            ]

        self.sync += [
            If(reduce(or_, [i.readable for i in initfifos]),
                self.cycle_count.eq(0)
            ).Elif(~self.core.global_inactive,
                self.cycle_count.eq(self.cycle_count + 1)
            )
        ]

        hmc_perf_counters = [Signal(32) for _ in range(9)]
        for i in range(9):
            port = config.platform.getHMCPort(i)
            self.sync += If(port.cmd_valid & port.cmd_ready, hmc_perf_counters[i].eq(hmc_perf_counters[i]+1))
            self.comb += [
                port.wr_data.eq(0),
                port.wr_data_valid.eq(0)
            ]



        hmc_perf_counters_pico = [Signal(32) for _ in hmc_perf_counters]
        self.submodules.perf_counter_transfer = BusSynchronizer(len(hmc_perf_counters)*len(hmc_perf_counters[0]), "sys", "pico")
        self.comb += [
            self.perf_counter_transfer.i.eq(Cat(*hmc_perf_counters)),
            Cat(*hmc_perf_counters_pico).eq(self.perf_counter_transfer.o)
        ]

        if config.use_hmc:
            if num_pe < 10:
                status_regs_pico = [Signal(32) for _ in range(4*num_pe)]
                self.submodules.status_regs_transfer = BusSynchronizer(len(status_regs_pico)*len(status_regs_pico[0]), "sys", "pico")
                self.comb += [
                    self.status_regs_transfer.i.eq(Cat(sr for n in self.core.scatter for sr in (n.get_neighbors.num_requests_accepted, n.get_neighbors.num_hmc_commands_issued, n.get_neighbors.num_hmc_commands_retired, n.get_neighbors.num_hmc_responses))),
                    # self.status_regs_transfer.i.eq(Cat(sr for n in self.core.neighbors_hmc for sr in n.num_reqs + n.wrongs)),
                    Cat(*status_regs_pico).eq(self.status_regs_transfer.o)
                ]
            else:
                status_regs_pico = [Signal(32) for _ in range(4*9)]
                self.submodules.status_regs_transfer = BusSynchronizer(len(status_regs_pico)*len(status_regs_pico[0]), "sys", "pico")
                self.comb += [
                    self.status_regs_transfer.i.eq(Cat(sr for n in self.core.neighbors_hmc for sr in (n.num_requests_accepted, n.num_hmc_commands_issued, n.num_hmc_commands_retired, n.num_hmc_responses))),
                    # self.status_regs_transfer.i.eq(Cat(sr for n in self.core.neighbors_hmc for sr in n.num_reqs + n.wrongs)),
                    Cat(*status_regs_pico).eq(self.status_regs_transfer.o)
                ]
        else:
            status_regs_pico = [Signal(32) for _ in range(4*num_pe)]
            self.submodules.status_regs_transfer = BusSynchronizer(len(status_regs_pico)*len(status_regs_pico[0]), "sys", "pico")
            self.comb += [
                self.status_regs_transfer.i.eq(Cat(sr for n in self.core.scatter for sr in (n.get_neighbors.num_requests_accepted, n.get_neighbors.num_neighbors_issued))),
                # self.status_regs_transfer.i.eq(Cat(sr for n in self.core.neighbors_hmc for sr in n.num_reqs + n.wrongs)),
                Cat(*status_regs_pico).eq(self.status_regs_transfer.o)
            ]


        cycle_count_pico = Signal(len(self.cycle_count))
        self.submodules.cycle_count_transfer = BusSynchronizer(len(self.cycle_count), "sys", "pico")
        self.comb += [
            self.cycle_count_transfer.i.eq(self.cycle_count),
            cycle_count_pico.eq(self.cycle_count_transfer.o)
        ]

        start_pico = Signal()
        self.specials += [
            NoRetiming(start_pico),
            MultiReg(start_pico, start, odomain="sys")
        ]

        done_pico = Signal()
        self.specials += [
            NoRetiming(self.done),
            MultiReg(self.done, done_pico, odomain="pico")
        ]

        self.bus = config.platform.getBus()

        self.sync.pico += [
            If( self.bus.PicoRd & (self.bus.PicoAddr == 0x10000),
                self.bus.PicoDataOut.eq(cycle_count_pico)
            ),
            If( self.bus.PicoRd & (self.bus.PicoAddr == 0x10004),
                self.bus.PicoDataOut.eq(done_pico)
            ),
            [If( self.bus.PicoRd & (self.bus.PicoAddr == 0x10010 + i*4),
                self.bus.PicoDataOut.eq(csr)
            ) for i, csr in enumerate(hmc_perf_counters)],
            [If( self.bus.PicoRd & (self.bus.PicoAddr == 0x10100 + i*4),
                self.bus.PicoDataOut.eq(csr)
            ) for i, csr in enumerate(status_regs_pico)],
            If( self.bus.PicoWr & (self.bus.PicoAddr == 0x20000),
                start_pico.eq(1)
            )
        ]


def export(config, filename='StreamLoopback128_migen.v'):
    config.platform = PicoPlatform(bus_width=32, stream_width=128)

    m = Top(config)

    so = dict(migen.build.xilinx.common.xilinx_special_overrides)
    verilog.convert(m,
                    name="echo",
                    ios=config.platform.get_ios(),
                    special_overrides=so,
                    create_clock_domains=False
                    ).write(filename)
    if config.use_hmc:
        with open("adj_val.data", 'wb') as f:
            for x in config.adj_val:
                f.write(struct.pack('=I', x))

def sim(config):
    config.platform = PicoPlatform(bus_width=32, stream_width=128)
    tb = Core(config)
    generators = []

    if config.use_hmc:
        generators.extend([port.gen_responses(config.adj_val) for port in config.platform.HMCports])

    generators.extend([tb.gen_input()])
    generators.extend([tb.gen_barrier_monitor()])
    generators.extend([s.get_neighbors.gen_selfcheck(tb, config.adj_dict, quiet=False) for s in tb.scatter])
    generators.extend([a.gen_selfcheck(tb) for a in tb.network.arbiter])
    generators.extend([a.applykernel.gen_selfcheck(tb, quiet=True) for a in tb.apply])
    # generators.extend([a.scatterkernel.gen_selfcheck(tb, quiet=False) for a in tb.scatter])

    # generators.extend([a.gen_stats(tb) for a in tb.apply])
    # generators.extend([tb.gen_network_stats()])
    run_simulation(tb, generators, vcd_name="tb.vcd")


def main():
    logging.basicConfig(level=logging.DEBUG,
                        format='%(name)-25s %(levelname)-8s %(message)s',
                        datefmt='%m-%d %H:%M',
                        filename='fpgagraphlib.log',
                        filemode='w')
    # define a Handler which writes INFO messages or higher to the sys.stderr
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    # set a format which is simpler for console use
    formatter = logging.Formatter('%(name)-25s: %(levelname)-8s %(message)s')
    # tell the handler to use this format
    console.setFormatter(formatter)
    # add the handler to the root logger
    logging.getLogger('').addHandler(console)

    logger = logging.getLogger('config')

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-f', '--from-file', dest='graphfile',
                        help='filename containing graph')
    parser.add_argument('-n', '--nodes', type=int,
                        help='number of nodes to generate')
    parser.add_argument('-e', '--edges', type=int,
                        help='number of edges to generate')
    parser.add_argument('-d', '--digraph', action="store_true", help='graph is directed (default is undirected)')
    parser.add_argument('-s', '--seed', type=int,
                        help='seed to initialise random number generator')
    parser.add_argument('--random-walk', action='store_const',
                        const='random_walk', dest='approach',
                        help='use a random-walk generation algorithm (default)')
    parser.add_argument('--naive', action='store_const',
                        const='naive', dest='approach',
                        help='use a naive generation algorithm (slower)')
    parser.add_argument('--partition', action='store_const',
                        const='partition', dest='approach',
                        help='use a partition-based generation algorithm (biased)')
    parser.add_argument('--save-graph', dest='graphsave', help='save graph to a file')
    parser.add_argument('command', help="one of 'sim' or 'export'")
    parser.add_argument('-o', '--output', help="output file name to save verilog export (valid with command 'export' only)")
    args = parser.parse_args()

    if args.seed:
        s = args.seed
    else:
        s = 42
    random.seed(s)

    if args.graphfile:
        logger.info("Reading graph from file {}".format(args.graphfile))
        graphfile = open(args.graphfile)
        adj_dict = read_graph(graphfile)
    elif args.nodes:
        num_nodes = args.nodes
        if args.edges:
            num_edges = args.edges
        else:
            num_edges = num_nodes - 1
        if args.approach:
            approach = args.approach
        else:
            approach = "random_walk"
        logger.info("Generating graph with {} nodes and {} edges".format(num_nodes, num_edges))
        adj_dict = generate_graph(num_nodes, num_edges, approach=approach, digraph=args.digraph)
    else:
        parser.print_help()
        exit(-1)

    if args.graphsave:
        logger.info("Saving graph to file {}".format(args.graphsave))
        export_graph(adj_dict, args.graphsave)

    config = Config(adj_dict)

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
