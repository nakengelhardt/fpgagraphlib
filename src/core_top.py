from migen import *
from tbsupport import *
import migen.build.xilinx.common
from migen.genlib.resetsync import AsyncResetSynchronizer


from functools import reduce
from operator import or_

import riffa

# import unittest
import random
import sys
import argparse

from recordfifo import RecordFIFO
from graph_input import read_graph
from graph_generate import generate_graph, export_graph
from core_core_tb import Core
from core_interfaces import Message

from pr.config import Config


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

        rlen = Signal(32)
        rcount = Signal(32)
        fsm.act("IDLE",
            NextValue(rcount, 0),
            NextValue(rlen, rx.len),
            If(self.done & rx.start,
                NextState("RECEIVE")
            )
        )
        fsm.act("RECEIVE",
            rx.ack.eq(1),
            If(rx.data_valid,
                rx.data_ren.eq(1),
                NextValue(rcount, rcount + 4),
                # NextValue(self.core.apply[0].extern_rd_port.adr, rx.data),
                # NextValue(self.core.apply[0].extern_rd_port.re, 1),
                # NextValue(self.core.apply[0].extern_rd_port.enable, 1),
                If(rcount + 4 >= rlen,
                    NextState("TRANSMIT")
                )
            )
        )
        fsm.act("TRANSMIT",
            tx.start.eq(1),
            tx.len.eq(4),
            tx.data_valid.eq(1),
            tx.last.eq(1),
            If(tx.data_ren,
                # NextValue(self.core.apply[0].extern_rd_port.enable, 0),
                NextState("IDLE")
            )
        )
        self.comb += [
            tx.data.eq(Cat(self.cycle_count, self.done)) #self.core.apply[0].extern_rd_port.dat_r[-32:],
        ]

class WrappedTop(riffa.GenericRiffa):
    def __init__(self, config, combined_interface_rx, combined_interface_tx, c_pci_data_width=128):
        riffa.GenericRiffa.__init__(self, combined_interface_rx=combined_interface_rx, combined_interface_tx=combined_interface_tx, c_pci_data_width=c_pci_data_width)
        rx, tx = self.get_channel(0)
        self.submodules.top = Top(config=config, rx=rx, tx=tx)
        self.ext_clk = Signal()
        self.ext_rst = Signal()
        pll_locked = Signal()
        pll_fb = Signal()
        pll_sys = Signal()
        self.specials += [
            Instance("PLLE2_BASE",
                     p_STARTUP_WAIT="TRUE", o_LOCKED=pll_locked,

                     # VCO @ 1GHz
                     p_REF_JITTER1=0.01, p_CLKIN1_PERIOD=4.0,
                     p_CLKFBOUT_MULT=6, p_DIVCLK_DIVIDE=1,
                     i_CLKIN1=self.ext_clk, i_CLKFBIN=pll_fb, o_CLKFBOUT=pll_fb,

                     # 125MHz
                     p_CLKOUT0_DIVIDE=20, p_CLKOUT0_PHASE=0.0, o_CLKOUT0=pll_sys,

                     # 500MHz
                     p_CLKOUT1_DIVIDE=2, p_CLKOUT1_PHASE=0.0, #o_CLKOUT1=pll_sys4x,

                     # 200MHz
                     p_CLKOUT2_DIVIDE=5, p_CLKOUT2_PHASE=0.0, #o_CLKOUT2=pll_clk200,

                     p_CLKOUT3_DIVIDE=2, p_CLKOUT3_PHASE=0.0, #o_CLKOUT3=,

                     p_CLKOUT4_DIVIDE=4, p_CLKOUT4_PHASE=0.0, #o_CLKOUT4=
            ),
            Instance("BUFG", i_I=pll_sys, o_O=self.cd_sys.clk),
            AsyncResetSynchronizer(self.cd_sys, ~pll_locked)
        ]

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
    so = dict(migen.build.xilinx.common.xilinx_special_overrides)
    so.update(migen.build.xilinx.common.xilinx_s7_special_overrides)
    verilog.convert(m, 
                    name="top", 
                    ios=( { getattr(combined_interface_rx, name) for name in ["start", "ack", "last", "len", "off", "data", "data_valid", "data_ren"]} 
                        | {getattr(combined_interface_tx, name) for name in ["start", "ack", "last", "len", "off", "data", "data_valid", "data_ren"]} 
                        | {m.rx_clk, m.tx_clk, m.ext_clk, m.ext_rst}),
                    special_overrides=so
                    ).write(filename)


def sim(config):
    rx = riffa.Interface(data_width=128, num_chnls=1)
    tx = riffa.Interface(data_width=128, num_chnls=1)
    tb = Top(config, rx, tx)
    generators = []
    generators.extend([riffa.gen_channel_write(rx, [1])])
    generators.extend([riffa.gen_channel_read(tx)])
    
    # generators.extend([tb.core.gen_barrier_monitor()])
    generators.extend([s.get_neighbors.gen_selfcheck(tb.core, config.adj_dict, quiet=True) for s in tb.core.scatter])
    # generators.extend([a.gen_selfcheck(tb.core, quiet=True) for a in tb.core.network.arbiter])
    generators.extend([a.applykernel.gen_selfcheck(tb.core, quiet=False) for a in tb.core.apply])
    # generators.extend([a.scatterkernel.gen_selfcheck(tb.core, quiet=False) for a in tb.core.scatter])
    
    # generators.extend([a.gen_stats(tb.core) for a in tb.core.apply])
    # generators.extend([tb.core.gen_network_stats()])
    run_simulation(tb, generators)#, vcd_name="tb.vcd")


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
        adj_dict = generate_graph(num_nodes, num_edges, approach=approach, digraph=args.digraph)
    else:
        parser.print_help()
        exit(-1)

    if args.graphsave:
            export_graph(adj_dict, args.graphsave)

    # print(adj_dict)
    config = Config(adj_dict, quiet=False)

    if args.command=='sim':
        sim(config)
    if args.command=='export':
        filename = "top.v"
        if args.output:
            filename = args.output
        export(config, filename=filename)
    

if __name__ == '__main__':
    main()