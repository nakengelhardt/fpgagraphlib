from migen import *
from tbsupport import *

from functools import reduce
from operator import or_

import riffa

import unittest
import random
import sys
import argparse

from recordfifo import RecordFIFO
from graph_input import read_graph
from graph_generate import generate_graph
from core_core_tb import Core
from core_interfaces import Message

from bfs.config import Config




class Top(Module):
    def __init__(self, config, tx):
        self.config = config
        num_pe = config.addresslayout.num_pe
        
        self.submodules.core = Core(config)
        
        start_message = [self.core.arbiter[i].start_message for i in range(num_pe)]
        layout = Message(**config.addresslayout.get_params()).layout
        initdata = [[convert_record_tuple_to_int((0, dest_id, 0, payload), layout) for dest_id, payload in init_message] for init_message in config.init_messages]
        for i in initdata:
            i.append(convert_record_tuple_to_int((1, 0, 0, 0), layout))
        initfifos = [RecordFIFO(layout=layout, depth=len(ini)+1, init=ini) for ini in initdata]
        
        for i in range(num_pe):
            initfifos[i].readable.name_override = "initfifos{}_readable".format(i)
            initfifos[i].re.name_override = "initfifos{}_re".format(i)
            initfifos[i].dout.name_override = "initfifos{}_dout".format(i)
            
        self.submodules += initfifos

        init = Signal()
        self.done = Signal()
        self.cycle_count = Signal(32)
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
        fsm.act("WAIT",
            If(self.done,
               NextState("SEND_RES_START")
            )
        )
        fsm.act("SEND_RES_START",
            tx.start.eq(1),
            tx.len.eq(1),
            tx.last.eq(1),
            tx.off.eq(0),
            If(tx.ack,
               NextState("SEND_RES")
            )
        )
        fsm.act("SEND_RES",
            tx.start.eq(1),
            tx.len.eq(1),
            tx.last.eq(1),
            tx.off.eq(0),
            tx.data.eq(self.cycle_count),
            tx.data_valid.eq(1),
            If(tx.ack,
               NextState("SEND_RES")
            )
        )

    def gen_output(self, tx):
        ret = yield from riffa.gen_channel_read(tx)
        print(ret)

class WrappedTop(riffa.GenericRiffa):
    def __init__(self, config, combined_interface_rx, combined_interface_tx, c_pci_data_width=128):
        riffa.GenericRiffa.__init__(self, combined_interface_rx=combined_interface_rx, combined_interface_tx=combined_interface_tx, c_pci_data_width=c_pci_data_width)
        rx, tx = self.get_channel(0)
        self.submodules.top = Top(config=config, tx=tx)
        self.ext_clk = Signal()
        self.ext_rst = Signal()
        rst1 = Signal()
        self.specials += [
            Instance("FDPE", p_INIT=1, i_D=0, i_PRE=self.ext_rst,
                i_CE=1, i_C=self.cd_sys.clk, o_Q=rst1),
            Instance("FDPE", p_INIT=1, i_D=rst1, i_PRE=self.ext_rst,
                i_CE=1, i_C=self.cd_sys.clk, o_Q=self.cd_sys.rst)
        ]
        self.comb += self.cd_sys.clk.eq(self.ext_clk)

def export(config, filename='top.v'):
    c_pci_data_width = 128
    num_chnls = 2
    combined_interface_tx = riffa.Interface(data_width=c_pci_data_width, num_chnls=num_chnls)
    combined_interface_rx = riffa.Interface(data_width=c_pci_data_width, num_chnls=num_chnls)

    m = WrappedTop(config, combined_interface_rx, combined_interface_tx, c_pci_data_width=c_pci_data_width)

    # add a loopback to test responsiveness
    test_rx, test_tx = m.get_channel(num_chnls - 1)
    m.comb += test_rx.connect(test_tx)

    m.ext_clk.name_override="clk"
    m.ext_rst.name_override="rst"
    for name in "ack", "last", "len", "off", "data", "data_valid", "data_ren":
        getattr(combined_interface_rx, name).name_override="chnl_rx_{}".format(name)
        getattr(combined_interface_tx, name).name_override="chnl_tx_{}".format(name)
    combined_interface_rx.start.name_override="chnl_rx"
    combined_interface_tx.start.name_override="chnl_tx"
    m.rx_clk.name_override="chnl_rx_clk"
    m.tx_clk.name_override="chnl_tx_clk"
    verilog.convert(m, 
                    name="top", 
                    ios=( { getattr(combined_interface_rx, name) for name in ["start", "ack", "last", "len", "off", "data", "data_valid", "data_ren"]} 
                        | {getattr(combined_interface_tx, name) for name in ["start", "ack", "last", "len", "off", "data", "data_valid", "data_ren"]} 
                        | {m.rx_clk, m.tx_clk, m.ext_clk, m.ext_rst}) 
                    ).write(filename)

def sim(config):
    tx = riffa.Interface(data_width=128, num_chnls=1)
    tb = Top(config, tx)
    generators = []
    generators.extend([tb.gen_output(tx), tb.core.gen_barrier_monitor()])
    generators.extend([a.applykernel.gen_selfcheck(tb.core, quiet=True) for a in tb.core.apply])
    # generators.extend([s.get_neighbors.gen_selfcheck(tb, adj_dict, quiet=True) for s in tb.scatter])
    # generators.extend([a.gen_selfcheck(tb, quiet=True) for a in tb.arbiter])
    run_simulation(tb, generators, vcd_name="tb.vcd")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-f', '--from-file', dest='graphfile',
                        help='filename containing graph')
    parser.add_argument('-n', '--nodes', type=int,
                        help='number of nodes to generate')
    parser.add_argument('-e', '--edges', type=int,
                        help='number of edges to generate')
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
    parser.add_argument('command', help="one of 'sim' or 'export'")
    parser.add_argument('-o', '--output', help="output file name to save verilog exprt (for command 'export')")
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
        adj_dict = generate_graph(num_nodes, num_edges, approach=approach)
    else:
        parser.print_help()
        exit(-1)

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