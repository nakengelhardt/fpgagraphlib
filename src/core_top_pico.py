from migen import *
from tbsupport import *
from migen.fhdl import verilog
import migen.build.xilinx.common
from migen.genlib.resetsync import AsyncResetSynchronizer
from migen.genlib.cdc import *

import logging

from functools import reduce
from operator import or_, and_

from pico import PicoPlatform

from core_init import init_parse

from recordfifo import RecordFIFO
from core_interfaces import Message
from fifo_network import Network
from core_apply import Apply
from core_scatter import Scatter
from core_neighbors_hmcx4 import Neighborsx4

class Core(Module):
    def __init__(self, config):
        self.config = config
        num_pe = self.config.addresslayout.num_pe

        if config.has_edgedata:
            init_edgedata = config.init_edgedata
        else:
            init_edgedata = [None for _ in range(num_pe)]

        self.submodules.network = Network(config)
        self.submodules.apply = [Apply(config, i, config.init_nodedata[i] if config.init_nodedata else None) for i in range(num_pe)]


        if config.use_hmc:
            if not config.share_mem_port:
                self.submodules.scatter = [Scatter(i, config, adj_mat=(config.adj_idx[i], config.adj_val[i]), edge_data=init_edgedata[i], hmc_port=config.platform.getHMCPort(i)) for i in range(num_pe)]
            else:
                assert(num_pe <= 36)
                # assert((num_pe % 4) == 0)
                self.submodules.scatter = [Scatter(i, config, adj_mat=(config.adj_idx[i], config.adj_val[i]), edge_data=init_edgedata[i]) for i in range(num_pe)]
                self.submodules.neighbors_hmc = [Neighborsx4(pe_id=i*4, config=config, hmc_port=config.platform.getHMCPort(i)) for i in range(9)]
                for j in range(4):
                    for i in range(9):
                        n = j*4 + i
                        if n < num_pe:
                            self.comb += [
                                self.scatter[n].get_neighbors.neighbor_in.connect(self.neighbors_hmc[i].neighbor_in[j]),
                                self.neighbors_hmc[i].neighbor_out[j].connect(self.scatter[n].get_neighbors.neighbor_out)
                            ]
        else:
            self.submodules.scatter = [Scatter(i, config, adj_mat=(config.adj_idx[i], config.adj_val[i]), edge_data=init_edgedata[i]) for i in range(num_pe)]

        # connect within PEs
        self.comb += [self.apply[i].scatter_interface.connect(self.scatter[i].scatter_interface) for i in range(num_pe)]

        # connect to network
        self.comb += [self.network.apply_interface[i].connect(self.apply[i].apply_interface) for i in range(num_pe)]
        self.comb += [self.scatter[i].network_interface.connect(self.network.network_interface[i]) for i in range(num_pe)]

        # state of calculation
        self.global_inactive = Signal()
        self.comb += self.global_inactive.eq(reduce(and_, [pe.inactive for pe in self.apply]))

    def gen_barrier_monitor(self, tb):
        logger = logging.getLogger('simulation.barriermonitor')
        num_pe = self.config.addresslayout.num_pe
        num_cycles = 0
        while not (yield self.global_inactive):
            num_cycles += 1
            for i in range(num_pe):
                if ((yield self.apply[i].apply_interface.valid)
                    and (yield self.apply[i].apply_interface.ack)):
                    if (yield self.apply[i].apply_interface.msg.barrier):
                        logger.debug(str(num_cycles) + ": Barrier enters Apply on PE " + str(i))
                    # else:
                    #     logger.debug(str(num_cycles) + ": Message for node {} (apply)".format((yield self.apply[i].apply_interface.msg.dest_id)))
                if ((yield self.apply[i].gatherkernel.valid_in)
                    and (yield self.apply[i].gatherkernel.ready)):
                    if ((yield self.apply[i].level) - 1) % self.config.addresslayout.num_channels != (yield self.apply[i].roundpar):
                        logger.warning("{}: received message's parity ({}) does not match current round ({})".format(num_cycles, (yield self.apply[i].roundpar), (yield self.apply[i].level)))
                if ((yield self.apply[i].scatter_interface.barrier)
                    and (yield self.apply[i].scatter_interface.valid)
                    and (yield self.apply[i].scatter_interface.ack)):
                    logger.debug(str(num_cycles) + ": Barrier exits Apply on PE " + str(i))
                if ((yield self.scatter[i].scatter_interface.valid)
                    and (yield self.scatter[i].scatter_interface.ack)):
                    if (yield self.scatter[i].scatter_interface.barrier):
                        logger.debug(str(num_cycles) + ": Barrier enters Scatter on PE " + str(i))
                    # else:
                    #     logger.debug(str(num_cycles) + ": Scatter from node {}".format((yield self.scatter[i].scatter_interface.sender)))
                if ((yield self.scatter[i].barrierdistributor.network_interface_in.valid)
                    and (yield self.scatter[i].barrierdistributor.network_interface_in.ack)):
                    if (yield self.scatter[i].barrierdistributor.network_interface_in.msg.barrier):
                        logger.debug(str(num_cycles) + ": Barrier exits Scatter on PE " + str(i))
                    # else:
                    #     logger.debug(str(num_cycles) + ": Message for node {} (scatter)".format((yield self.scatter[i].network_interface.msg.dest_id)))
            yield


class UnCore(Module):
    def __init__(self, config):
        self.config = config
        num_pe = config.addresslayout.num_pe

        self.submodules.cores = [Core(config)]

        self.global_inactive = Signal()
        self.comb += self.global_inactive.eq(self.cores[0].global_inactive)

        start_message = [a.start_message for core in self.cores for a in core.network.arbiter]
        layout = Message(**config.addresslayout.get_params()).layout
        initdata = [[convert_record_to_int(layout, barrier=0, roundpar=config.addresslayout.num_channels-1, dest_id=msg['dest_id'], sender=msg['sender'], payload=msg['payload'], halt=0) for msg in init_message] for init_message in config.init_messages]
        for i in initdata:
            i.append(convert_record_to_int(layout, barrier=1, roundpar=config.addresslayout.num_channels-1))
        initfifos = [RecordFIFO(layout=layout, depth=len(ini)+1, init=ini) for ini in initdata]

        for i in range(num_pe):
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
            ).Elif(~self.global_inactive,
                self.cycle_count.eq(self.cycle_count + 1)
            )
        ]

        self.total_num_messages = Signal(32)
        self.comb += [
            self.total_num_messages.eq(sum(scatter.barrierdistributor.total_num_messages for scatter in self.cores[0].scatter))
        ]

    def gen_simulation(self, tb):
        yield self.start.eq(1)
        yield

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
        num_pe = config.addresslayout.num_pe

        self.submodules.uncore = UnCore(config)

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

        hmc_perf_counters = []
        if config.use_hmc:
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

            if not config.share_mem_port:
                status_regs_pico = [Signal(32) for _ in range(4*num_pe)]
                self.submodules.status_regs_transfer = BusSynchronizer(len(status_regs_pico)*len(status_regs_pico[0]), "sys", "pico")
                self.comb += [
                    self.status_regs_transfer.i.eq(Cat(sr for core in self.uncore.cores for n in core.scatter for sr in (n.get_neighbors.num_requests_accepted, n.get_neighbors.num_hmc_commands_issued, n.get_neighbors.num_hmc_responses, n.get_neighbors.num_hmc_commands_retired))),
                    # self.status_regs_transfer.i.eq(Cat(sr for core in self.uncore.cores for n in core.neighbors_hmc for sr in n.num_reqs + n.wrongs)),
                    Cat(*status_regs_pico).eq(self.status_regs_transfer.o)
                ]
            else:
                status_regs_pico = [Signal(32) for _ in range(4*9)]
                self.submodules.status_regs_transfer = BusSynchronizer(len(status_regs_pico)*len(status_regs_pico[0]), "sys", "pico")
                self.comb += [
                    self.status_regs_transfer.i.eq(Cat(sr for core in self.uncore.cores for n in core.neighbors_hmc for sr in (n.num_requests_accepted, n.num_hmc_commands_issued))),
                    # self.status_regs_transfer.i.eq(Cat(sr for core in self.uncore.cores for n in core.neighbors_hmc for sr in n.num_reqs + n.wrongs)),
                    Cat(*status_regs_pico).eq(self.status_regs_transfer.o)
                ]
        else:
            status_regs_pico = [Signal(32) for _ in range(4*num_pe)]
            self.submodules.status_regs_transfer = BusSynchronizer(len(status_regs_pico)*len(status_regs_pico[0]), "sys", "pico")
            self.comb += [
                self.status_regs_transfer.i.eq(Cat(sr for core in self.uncore.cores for n in core.scatter for sr in (n.get_neighbors.num_requests_accepted, n.get_neighbors.num_neighbors_issued))),
                # self.status_regs_transfer.i.eq(Cat(sr for core in self.uncore.cores for n in core.neighbors_hmc for sr in n.num_reqs + n.wrongs)),
                Cat(*status_regs_pico).eq(self.status_regs_transfer.o)
            ]


        cycle_count_pico = Signal(len(self.uncore.cycle_count))
        self.submodules.cycle_count_transfer = BusSynchronizer(len(self.uncore.cycle_count), "sys", "pico")
        self.comb += [
            self.cycle_count_transfer.i.eq(self.uncore.cycle_count),
            cycle_count_pico.eq(self.cycle_count_transfer.o)
        ]

        total_num_messages_pico = Signal(len(self.uncore.total_num_messages))
        self.submodules.total_num_messages_transfer = BusSynchronizer(len(self.uncore.total_num_messages), "sys", "pico")
        self.comb += [
            self.total_num_messages_transfer.i.eq(self.uncore.total_num_messages),
            total_num_messages_pico.eq(self.total_num_messages_transfer.o)
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
            If( self.bus.PicoRd & (self.bus.PicoAddr == 0x10008),
                self.bus.PicoDataOut.eq(total_num_messages_pico)
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

def export(config, filename='top.v'):
    config.platform = PicoPlatform(config.addresslayout.num_pe, bus_width=32, stream_width=128)

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
    config.platform = PicoPlatform(config.addresslayout.num_pe, bus_width=32, stream_width=128)
    tb = UnCore(config)
    tb.submodules += config.platform
    generators = []

    if config.use_hmc:
        generators.extend(config.platform.getSimGenerators(config.adj_val))

    generators.extend([core.gen_barrier_monitor(tb) for core in tb.cores])
    generators.extend(get_simulators(tb, 'gen_selfcheck', tb))
    generators.extend(get_simulators(tb, 'gen_simulation', tb))

    # generators.extend([a.gen_stats(tb) for a in tb.apply])
    # generators.extend([tb.gen_network_stats()])
    run_simulation(tb, generators, vcd_name="tb.vcd")


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
