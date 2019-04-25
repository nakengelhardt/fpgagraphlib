from migen import *
from tbsupport import *
from migen.fhdl import verilog
import migen.build.xilinx.common
from migen.genlib.resetsync import AsyncResetSynchronizer
from migen.genlib.cdc import *

import logging
import subprocess

from functools import reduce
from operator import or_, and_

from pico import PicoPlatform

from core_init import init_parse

from recordfifo import RecordFIFO
from core_interfaces import *
from inverted_network import UpdateNetwork
from inverted_apply import Apply
from inverted_scatter import Scatter

class Core(Module):
    def __init__(self, config):
        self.config = config
        num_pe = self.config.addresslayout.num_pe

        if config.has_edgedata:
            init_edgedata = config.init_edgedata
        else:
            init_edgedata = [None for _ in range(num_pe)]


        self.submodules.apply = [Apply(config, i) for i in range(num_pe)]

        self.submodules.scatter = [Scatter(i, config) for i in range(num_pe)]

        self.submodules.network = UpdateNetwork(config)

        # choose between init and regular message channel
        self.start_message = [ApplyInterface(name="start_message", **config.addresslayout.get_params()) for i in range(num_pe)]
        for i in range(num_pe):
            self.start_message[i].select = Signal()
            self.comb += [
                If(self.start_message[i].select,
                    self.start_message[i].connect(self.apply[i].apply_interface)
                ).Else(
                    self.scatter[i].apply_interface.connect(self.apply[i].apply_interface)
                )
            ]

        # connect among PEs

        for i in range(num_pe):
            self.comb += [
                self.apply[i].scatter_interface.connect(self.network.apply_interface_in[i]),
                self.network.scatter_interface_out[i].connect(self.scatter[i].scatter_interface)
            ]


        # state of calculation
        self.global_inactive = self.network.inactive

        self.kernel_error = Signal()
        self.comb += self.kernel_error.eq(reduce(or_, [pe.gatherapplykernel.kernel_error for pe in self.apply]))

        self.deadlock = Signal()
        self.comb += self.deadlock.eq(reduce(or_, [pe.deadlock for pe in self.apply]))

        self.total_num_messages = Signal(32)
        self.comb += [
            self.total_num_messages.eq(sum(s.total_num_messages for s in self.scatter))
        ]

    def gen_barrier_monitor(self, tb):
        logger = logging.getLogger('sim.barriermonitor')
        num_pe = self.config.addresslayout.num_pe

        num_cycles = 0
        while not (yield tb.global_inactive):
            num_cycles += 1
            for a in self.apply:
                if ((yield a.apply_interface.valid) and (yield a.apply_interface.ack)):
                    if (yield a.apply_interface.msg.barrier):
                        logger.debug(str(num_cycles) + ": Barrier enters Apply on PE " + str(a.pe_id))
                if (yield a.gatherapplykernel.valid_in) and (yield a.gatherapplykernel.ready):
                    if (yield a.level) % self.config.addresslayout.num_channels != (yield a.gatherapplykernel.round_in):
                        logger.warning("{}: received message's parity ({}) does not match current round ({})".format(num_cycles, (yield a.roundpar), (yield a.level)))
                if ((yield a.scatter_interface.msg.barrier) and (yield a.scatter_interface.valid) and (yield a.scatter_interface.ack)):
                    logger.debug(str(num_cycles) + ": Barrier exits Apply on PE " + str(a.pe_id))
            for s in self.scatter:
                if ((yield s.scatter_interface.valid) and (yield s.scatter_interface.ack)):
                    if (yield s.scatter_interface.barrier):
                        logger.debug(str(num_cycles) + ": Barrier enters Scatter on PE " + str(s.pe_id))
                if ((yield s.apply_interface.valid) and (yield s.apply_interface.ack)):
                    if (yield s.apply_interface.msg.barrier):
                        logger.debug(str(num_cycles) + ": Barrier exits Scatter on PE " + str(s.pe_id))
            yield


class UnCore(Module):
    def __init__(self, config):
        self.config = config
        num_pe = config.addresslayout.num_pe

        self.submodules.cores = [Core(config)]

        self.global_inactive = self.cores[0].global_inactive
        self.kernel_error = self.cores[0].kernel_error
        self.deadlock = self.cores[0].deadlock

        start_message = self.cores[0].start_message

        injected = [Signal() for i in range(num_pe)]

        self.start = Signal()
        init = Signal()
        self.done = Signal()
        self.cycle_count = Signal(32)

        self.sync += [
            init.eq(self.start & ~reduce(and_, injected))
        ]

        self.comb += [
            self.done.eq(~init & self.global_inactive)
        ]

        for i in range(num_pe):
            self.comb += [
                start_message[i].select.eq(init),
                start_message[i].msg.barrier.eq(1),
                start_message[i].msg.roundpar.eq(config.addresslayout.num_channels-1),
                start_message[i].valid.eq(~injected[i])
            ]

        self.sync += [
            [If(start_message[i].ack, injected[i].eq(1)) for i in range(num_pe)],
            If(~reduce(and_, injected),
                self.cycle_count.eq(0)
            ).Elif(~self.global_inactive,
                self.cycle_count.eq(self.cycle_count + 1)
            )
        ]

        self.total_num_messages = self.cores[0].total_num_messages

    def gen_simulation(self, tb):
        yield self.start.eq(1)
        while not (yield self.global_inactive):
            yield
        logger = logging.getLogger('sim.start')
        logger.info("Total number of messages: {}".format((yield self.total_num_messages)))
        logger.info("Kernel error: {}".format((yield self.kernel_error)))


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

        hmc_perf_counters = [Signal(32) for _ in range(2*9)]
        for i in range(9):
            port = config.platform.picoHMCports[i]
            self.sync += [
                If(port.cmd_valid & port.cmd_ready, hmc_perf_counters[i].eq(hmc_perf_counters[i]+1)),
                If(port.rd_data_valid & ~port.dinv, hmc_perf_counters[i+9].eq(hmc_perf_counters[i+9]+1))
            ]

        hmc_perf_counters_pico = [Signal(32) for _ in hmc_perf_counters]
        for i in range(len(hmc_perf_counters)):
            self.specials += MultiReg(hmc_perf_counters[i], hmc_perf_counters_pico[i], odomain="bus")

        if config.memtype == "HMC" or config.memtype == "HMCO":
            status_regs = [sr for core in self.uncore.cores for n in core.scatter for sr in (n.get_neighbors.num_requests_accepted, n.get_neighbors.num_hmc_commands_issued, n.get_neighbors.num_hmc_responses, n.get_neighbors.num_hmc_commands_retired)]
        else:
            status_regs = []
            for core in self.uncore.cores:
                for i in range(num_pe):
                    status_regs.extend([
                        core.apply[i].barrierdistributor.total_num_updates,
                        # core.scatter[i].barrierdistributor.total_num_messages_in,
                        core.scatter[i].get_neighbors.num_updates_accepted,
                        core.scatter[i].get_neighbors.num_neighbors_issued,
                        core.apply[i].level,
                        #core.apply[i].gatherapplykernel.num_triangles,
                        core.scatter[i].get_neighbors.num_neighbors_issued,
                        #core.apply[i].outfifo.max_level,
                        # *core.scatter[i].barrierdistributor.prev_num_msgs_since_last_barrier,
                        # Cat(core.scatter[i].network_interface.valid, core.scatter[i].network_interface.ack, core.scatter[i].network_interface.msg.barrier, core.scatter[i].network_interface.msg.roundpar),
                        # Cat(core.apply[i].apply_interface.valid, core.apply[i].apply_interface.ack, core.apply[i].apply_interface.msg.barrier, core.apply[i].apply_interface.msg.roundpar),
                        # Cat(core.network.arbiter[i].barriercounter.apply_interface_in.valid, core.network.arbiter[i].barriercounter.apply_interface_in.ack, core.network.arbiter[i].barriercounter.apply_interface_in.msg.barrier, core.network.arbiter[i].barriercounter.apply_interface_in.msg.roundpar),
                        # Cat(core.network.arbiter[i].barriercounter.apply_interface_out.valid, core.network.arbiter[i].barriercounter.apply_interface_out.ack, core.network.arbiter[i].barriercounter.apply_interface_out.msg.barrier, core.network.arbiter[i].barriercounter.apply_interface_out.msg.roundpar),
                        # *core.network.arbiter[i].barriercounter.num_from_pe,
                        # *core.network.arbiter[i].barriercounter.num_expected_from_pe,
                        # Cat(*core.network.arbiter[i].barriercounter.barrier_from_pe),
                        # core.network.arbiter[i].barriercounter.round_accepting
                    ])

        status_regs_pico = [Signal(32) for _ in status_regs]
        for i in range(len(status_regs)):
            self.specials += MultiReg(status_regs[i], status_regs_pico[i], odomain="bus")

        cycle_count_pico = Signal(len(self.uncore.cycle_count))
        self.specials += MultiReg(self.uncore.cycle_count, cycle_count_pico, odomain="bus")

        total_num_messages_pico = Signal(len(self.uncore.total_num_messages))
        self.specials += MultiReg(self.uncore.total_num_messages, total_num_messages_pico, odomain="bus")

        start_pico = Signal()
        start_pico.attr.add("no_retiming")
        self.specials += [
            MultiReg(start_pico, self.uncore.start, odomain="sys")
        ]

        done_pico = Signal()
        self.uncore.done.attr.add("no_retiming")
        self.specials += [
            MultiReg(self.uncore.done, done_pico, odomain="bus")
        ]

        kernel_error_pico = Signal()
        self.uncore.kernel_error.attr.add("no_retiming")
        self.specials += [
            MultiReg(self.uncore.kernel_error, kernel_error_pico, odomain="bus")
        ]

        deadlock_pico = Signal()
        self.uncore.deadlock.attr.add("no_retiming")
        self.specials += [
            MultiReg(self.uncore.deadlock, deadlock_pico, odomain="bus")
        ]

        self.bus = config.platform.getBus()

        self.sync.bus += [
            If( self.bus.PicoRd & (self.bus.PicoAddr == 0x10000),
                self.bus.PicoDataOut.eq(cycle_count_pico)
            ),
            If( self.bus.PicoRd & (self.bus.PicoAddr == 0x10004),
                self.bus.PicoDataOut.eq(Cat(done_pico, kernel_error_pico, deadlock_pico))
            ),
            If( self.bus.PicoRd & (self.bus.PicoAddr == 0x10008),
                self.bus.PicoDataOut.eq(total_num_messages_pico)
            ),
            [If( self.bus.PicoRd & (self.bus.PicoAddr == 0x10010 + i*4),
                self.bus.PicoDataOut.eq(csr)
            ) for i, csr in enumerate(hmc_perf_counters_pico)],
            [If( self.bus.PicoRd & (self.bus.PicoAddr == 0x10100 + i*4),
                self.bus.PicoDataOut.eq(csr)
            ) for i, csr in enumerate(status_regs_pico)],
            If( self.bus.PicoWr & (self.bus.PicoAddr == 0x20000),
                start_pico.eq(1)
            )
        ]

def export(config, filename='top.v'):
    config.platform = PicoPlatform(0 if config.memtype == "BRAM" else config.addresslayout.num_pe_per_fpga, create_hmc_ios=True, bus_width=32, stream_width=128)

    m = Top(config)

    so = dict(migen.build.xilinx.common.xilinx_special_overrides)
    verilog.convert(m,
                    name="top",
                    ios=config.platform.get_ios(),
                    special_overrides=so,
                    create_clock_domains=False
                    ).write(filename)
    if config.memtype != "BRAM":
        export_data(config.adj_val, "adj_val.data", backup=config.alt_adj_val_data_name)

def sim(config):
    config.platform = PicoPlatform(0 if config.memtype == "BRAM" else config.addresslayout.num_pe_per_fpga, create_hmc_ios=True, bus_width=32, init=(config.adj_val if config.memtype != "BRAM" else []))
    tb = UnCore(config)
    tb.submodules += config.platform

    generators = config.platform.getSimGenerators()

    generators["sys"].extend([core.gen_barrier_monitor(tb) for core in tb.cores])
    generators["sys"].extend(get_simulators(tb, 'gen_selfcheck', tb))
    generators["sys"].extend(get_simulators(tb, 'gen_simulation', tb))

    # generators.extend([a.gen_stats(tb) for a in tb.apply])
    # generators.extend([tb.gen_network_stats()])
    run_simulation(tb, generators, clocks={"sys": 10, "bus": 480, "stream": 8}, vcd_name="{}.vcd".format(config.vcdname))


def main():
    args, config = init_parse(inverted=True)

    logger = logging.getLogger('config')

    if args.command=='sim':
        logger.info("Starting Simulation")
        sim(config)
    elif args.command=='export':
        filename = "top.v"
        if args.output:
            filename = args.output
        logger.info("Exporting design to file {}".format(filename))
        export(config, filename=filename)
    else:
        logger.error("Command should be one of: sim export")

if __name__ == '__main__':
    main()
