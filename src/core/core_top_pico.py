from migen import *
from tbsupport import *
from migen.fhdl import verilog
import migen.build.xilinx.common
from migen.genlib.resetsync import AsyncResetSynchronizer


from functools import reduce
from operator import or_

import pico

# import unittest
import random
import sys
import argparse

from recordfifo import RecordFIFO
from graph_input import read_graph
from graph_generate import generate_graph, export_graph
from core_core_tb import Core
from core_interfaces import Message

from bfs.config import Config

class Top(Module):
    def __init__(self, config, rx, tx):
        self.config = config
        num_pe = config.addresslayout.num_pe

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

        init = Signal()
        self.done = Signal()
        self.cycle_count = Signal(64)
        self.comb += [
            init.eq(reduce(or_, [i.readable for i in initfifos])),
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
            If(init,
                self.cycle_count.eq(0)
            ).Elif(~self.core.global_inactive,
                self.cycle_count.eq(self.cycle_count + 1)
            )
        ]

        fsm = FSM()
        self.submodules += fsm

        fsm.act("IDLE",
            rx.rdy.eq(self.done),
            If(rx.rdy & rx.valid,
                NextState("RECEIVE")
            )
        )

        fsm.act("RECEIVE",
            tx.valid.eq(1),
            If(tx.rdy,
                NextState("IDLE")
            )
        )

        self.comb += [
            tx.data.eq(Cat(self.cycle_count, self.done))
        ]


def export(config, filename='StreamLoopback128_migen.v'):
    data_width = 128
    num_chnls = 2
    rx = [pico.PicoStreamInterface(data_width=data_width) for i in range(num_chnls)]
    tx = [pico.PicoStreamInterface(data_width=data_width) for i in range(num_chnls)]

    m = Top(config, rx[0], tx[0])
    m.comb += [
        rx[1].connect(tx[1])
    ]

    m.clock_domains.cd_sys = ClockDomain()
    m.cd_sys.clk.name_override = "clk"
    m.cd_sys.rst.name_override = "rst"
    for i in range(num_chnls):
        for name in [x[0] for x in pico._stream_layout]:
            getattr(rx[i], name).name_override="s{}i_{}".format(i+1, name)
            getattr(tx[i], name).name_override="s{}o_{}".format(i+1, name)
    so = dict(migen.build.xilinx.common.xilinx_special_overrides)
    verilog.convert(m,
                    name="StreamLoopback128",
                    ios=( {getattr(rx[i], name) for i in range(num_chnls) for name in ["valid", "rdy", "data"]}
                        | {getattr(tx[i], name) for i in range(num_chnls) for name in ["valid", "rdy", "data"]}
                        | {m.cd_sys.clk, m.cd_sys.rst}),
                    special_overrides=so
                    ).write(filename)

def sim(config):
    rx = pico.PicoStreamInterface(data_width=128)
    tx = pico.PicoStreamInterface(data_width=128)
    tb = Top(config, rx, tx)
    generators = []
    generators.extend([pico.gen_channel_write(rx, [1])])
    generators.extend([pico.gen_channel_read(tx, 4)])

    # generators.extend([tb.core.gen_barrier_monitor()])
    generators.extend([s.get_neighbors.gen_selfcheck(tb.core, config.adj_dict, quiet=True) for s in tb.core.scatter])
    # generators.extend([a.gen_selfcheck(tb.core, quiet=True) for a in tb.core.network.arbiter])
    generators.extend([a.applykernel.gen_selfcheck(tb.core, quiet=False) for a in tb.core.apply])
    # generators.extend([a.scatterkernel.gen_selfcheck(tb.core, quiet=False) for a in tb.core.scatter])

    # generators.extend([a.gen_stats(tb.core) for a in tb.core.apply])
    # generators.extend([tb.core.gen_network_stats()])
    run_simulation(tb, generators, vcd_name="tb.vcd")


def main():
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
        adj_dict = generate_graph(num_nodes, num_edges, approach=approach, digraph=args.digraph)
    else:
        parser.print_help()
        exit(-1)

    if args.graphsave:
            export_graph(adj_dict, args.graphsave)

    # print(adj_dict)
    config = Config(adj_dict)

    if args.command=='sim':
        sim(config)
    if args.command=='export':
        filename = "top.v"
        if args.output:
            filename = args.output
        export(config, filename=filename)


if __name__ == '__main__':
    main()
