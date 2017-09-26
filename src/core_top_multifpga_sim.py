from migen.fhdl import verilog
import migen.build.xilinx.common

from migen import *
from migen.genlib.roundrobin import *
from migen.genlib.cdc import *
from tbsupport import *

from functools import reduce
from operator import and_

import logging
import random

from pico import PicoPlatform

from core_init import init_parse

from recordfifo import RecordFIFO
from core_core_tb import Core
from core_interfaces import Message

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

        for i in range(config.addresslayout.num_channels):
            ext_msg_channel_out = Array(core.network.external_network_interface_out[i].msg.raw_bits() for core in self.cores)
            ext_dest_pe_channel_out = Array(core.network.external_network_interface_out[i].dest_pe for core in self.cores)
            ext_valid_channel_out = Array(core.network.external_network_interface_out[i].valid for core in self.cores)
            ext_ack_channel_out = Array(core.network.external_network_interface_out[i].ack for core in self.cores)

            ext_msg_channel_in = Array(core.network.external_network_interface_in[i].msg.raw_bits() for core in self.cores)
            ext_dest_pe_channel_in = Array(core.network.external_network_interface_in[i].dest_pe for core in self.cores)
            ext_valid_channel_in = Array(core.network.external_network_interface_in[i].valid for core in self.cores)
            ext_ack_channel_in = Array(core.network.external_network_interface_in[i].ack for core in self.cores)

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
        with open("{}.net_stats.{}pe.{}groups.{}delay.log".format(self.config.name, self.config.addresslayout.num_pe, self.config.addresslayout.pe_groups, self.config.addresslayout.inter_pe_delay), 'w') as netstatsfile:
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

class Top(Module):
    def __init__(self, config):
        self.config = config
        num_pe = config.addresslayout.num_pe

        self.submodules += config.platform

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

        self.submodules.uncore = UnCore(config)

        status_regs_pico = [Signal(32) for _ in range(4*num_pe)]
        self.submodules.status_regs_transfer = BusSynchronizer(len(status_regs_pico)*len(status_regs_pico[0]), "sys", "pico")
        self.comb += [
            self.status_regs_transfer.i.eq(Cat(sr for core in self.uncore.cores for n in core.scatter for sr in (n.get_neighbors.num_requests_accepted, n.get_neighbors.num_neighbors_issued))),
            # self.status_regs_transfer.i.eq(Cat(sr for n in self.core.neighbors_hmc for sr in n.num_reqs + n.wrongs)),
            Cat(*status_regs_pico).eq(self.status_regs_transfer.o)
        ]

        cycle_count_pico = Signal(len(self.uncore.cycle_count))
        self.submodules.cycle_count_transfer = BusSynchronizer(len(self.uncore.cycle_count), "sys", "pico")
        self.comb += [
            self.cycle_count_transfer.i.eq(self.uncore.cycle_count),
            cycle_count_pico.eq(self.cycle_count_transfer.o)
        ]

        start_pico = Signal()
        start_pico.attr.add("no_retiming")
        self.specials += [
            MultiReg(start_pico, self.uncore.start, odomain="sys")
        ]

        done_pico = Signal()
        self.uncore.done.attr.add("no_retiming")
        self.specials += [
            MultiReg(self.uncore.done, done_pico, odomain="pico")
        ]

        self.bus = config.platform.getBus()

        self.sync.pico += [
            If( self.bus.PicoRd & (self.bus.PicoAddr == 0x10000),
                self.bus.PicoDataOut.eq(cycle_count_pico)
            ),
            If( self.bus.PicoRd & (self.bus.PicoAddr == 0x10004),
                self.bus.PicoDataOut.eq(done_pico)
            ),
            [If( self.bus.PicoRd & (self.bus.PicoAddr == 0x10100 + i*4),
                self.bus.PicoDataOut.eq(csr)
            ) for i, csr in enumerate(status_regs_pico)],
            If( self.bus.PicoWr & (self.bus.PicoAddr == 0x20000),
                start_pico.eq(1)
            )
        ]

def get_simulators(module, name, *args, **kwargs):
    simulators = []
    if hasattr(module, name):
        simulators.append(getattr(module, name)(*args, **kwargs))
    for _, submodule in module._submodules:
            for simulator in get_simulators(submodule, name, *args, **kwargs):
                    simulators.append(simulator)
    return simulators

def sim(config):

    tb = UnCore(config)

    generators = []

    for core in tb.cores:
        generators.extend([core.gen_barrier_monitor(tb)])

    generators.extend(get_simulators(tb, 'gen_selfcheck', tb))
    generators.extend(get_simulators(tb, 'gen_simulation', tb))

    run_simulation(tb, generators, vcd_name="tb.vcd")

def export(config, filename='top_multi.v'):
    config.platform = PicoPlatform(config.addresslayout.num_pe, bus_width=32, stream_width=128)

    m = Top(config)

    so = dict(migen.build.xilinx.common.xilinx_special_overrides)
    verilog.convert(m,
                    name="echo",
                    ios=config.platform.get_ios(),
                    special_overrides=so,
                    create_clock_domains=False
                    ).write(filename)

def main():
    args, config = init_parse()

    logger = logging.getLogger('config')

    if args.command=='sim':
        logger.info("Starting Simulation")
        sim(config)
    if args.command=='export':
        filename = "top_multi.v"
        if args.output:
            filename = args.output
        logger.info("Exporting design to file {}".format(filename))
        export(config, filename=filename)

if __name__ == '__main__':
    main()
