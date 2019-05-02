from migen import *
from tbsupport import *
from migen.fhdl import verilog
import migen.build.xilinx.common
from migen.genlib.resetsync import AsyncResetSynchronizer
from migen.genlib.cdc import *
from migen.genlib.fifo import *

import logging

from functools import reduce
from operator import or_, and_

from pico import PicoPlatform

from core_init import init_parse

from recordfifo import RecordFIFO
from core_interfaces import *
from inverted_network_multi import UpdateNetwork
from inverted_apply import Apply
from inverted_scatter import Scatter

class Core(Module):
    def __init__(self, config, fpga_id):
        self.config = config
        pe_start = fpga_id*config.addresslayout.num_pe_per_fpga
        pe_end = min((fpga_id+1)*config.addresslayout.num_pe_per_fpga, config.addresslayout.num_pe)
        self.pe_start = pe_start
        num_local_pe = pe_end - pe_start

        if config.has_edgedata:
            init_edgedata = config.init_edgedata
        else:
            init_edgedata = [None for _ in range(num_local_pe)]


        self.submodules.apply = [Apply(config, i) for i in range(pe_start, pe_end)]

        self.submodules.scatter = [Scatter(i, config, port=config.platform[fpga_id].getHMCPort(i-pe_start)) for i in range(pe_start, pe_end)]

        self.submodules.network = UpdateNetwork(config, fpga_id)

        # choose between init and regular message channel
        self.start_message = [ApplyInterface(name="start_message", **config.addresslayout.get_params()) for i in range(num_local_pe)]
        for i in range(num_local_pe):
            self.start_message[i].select = Signal()
            self.comb += [
                If(self.start_message[i].select,
                    self.start_message[i].connect(self.apply[i].apply_interface)
                ).Else(
                    self.scatter[i].apply_interface.connect(self.apply[i].apply_interface)
                )
            ]

        # connect among PEs

        for i in range(num_local_pe):
            self.comb += [
                self.apply[i].scatter_interface.connect(self.network.apply_interface_in[i]),
                self.network.scatter_interface_out[i].connect(self.scatter[i].scatter_interface)
            ]

        # state of calculation

        injected = [Signal() for i in range(num_local_pe)]

        self.start = Signal()
        init = Signal()
        self.done = Signal()
        self.cycle_count = Signal(32)
        self.global_inactive = self.network.inactive

        self.sync += [
            init.eq(self.start & ~reduce(and_, injected))
        ]

        self.comb += [
            self.done.eq(~init & self.global_inactive)
        ]

        for i in range(num_local_pe):
            self.comb += [
                self.start_message[i].select.eq(init),
                self.start_message[i].msg.barrier.eq(1),
                self.start_message[i].msg.roundpar.eq(config.addresslayout.num_channels-1),
                self.start_message[i].valid.eq(~injected[i])
            ]

        self.sync += [
            [If(self.start_message[i].ack, injected[i].eq(1)) for i in range(num_local_pe)],
            If(~reduce(and_, injected),
                self.cycle_count.eq(0)
            ).Elif(~self.global_inactive,
                self.cycle_count.eq(self.cycle_count + 1)
            )
        ]

        self.total_num_messages = Signal(32)
        self.comb += [
            self.total_num_messages.eq(sum(s.total_num_messages for s in self.scatter))
        ]

        # error reporting

        self.kernel_error = Signal()
        self.comb += self.kernel_error.eq(reduce(or_, [pe.gatherapplykernel.kernel_error for pe in self.apply]))

        self.deadlock = Signal()
        self.comb += self.deadlock.eq(reduce(or_, [pe.deadlock for pe in self.apply]))

    def gen_barrier_monitor(self, tb):
        logger = logging.getLogger('sim.barriermonitor')
        num_cycles = 0
        while not (yield tb.global_inactive):
            num_cycles += 1
            for a in self.apply:
                if ((yield a.apply_interface.valid) and (yield a.apply_interface.ack)):
                    if (yield a.apply_interface.msg.barrier):
                        logger.debug(str(num_cycles) + ": Barrier enters Apply on PE " + str(a.pe_id))
                if (yield a.gatherapplykernel.valid_in) and (yield a.gatherapplykernel.ready):
                    if (yield a.level) % self.config.addresslayout.num_channels != (yield a.gatherapplykernel.round_in):
                        logger.warning("{}: received message's parity ({}) does not match current round ({})".format(num_cycles, (yield a.gatherapplykernel.round_in), (yield a.level)))
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

class AllInOneUnCore(Module):
    def __init__(self, config):
        self.config = config
        num_pe = config.addresslayout.num_pe

        self.submodules.cores = [Core(config, i) for i in range(config.addresslayout.num_fpga)]

        self.start = Signal()
        self.done = Signal()
        self.kernel_error = Signal()
        self.deadlock = Signal()
        self.global_inactive = Signal()
        self.total_num_messages = Signal(32)
        self.cycle_count = Signal(64)

        self.comb += [
            self.global_inactive.eq(reduce(and_, (core.global_inactive for core in self.cores))),
            self.done.eq(reduce(and_, (core.done for core in self.cores))),
            [core.start.eq(self.start) for core in self.cores],
            self.kernel_error.eq(reduce(or_, (core.kernel_error for core in self.cores))),
            self.deadlock.eq(reduce(or_, (core.deadlock for core in self.cores))),
            self.total_num_messages.eq(sum(core.total_num_messages for core in self.cores)),
            self.cycle_count.eq(self.cores[0].cycle_count)
        ]

        # inter-core communication
        for i in range(config.addresslayout.num_fpga):
            core_idx = 0
            for j in range(config.addresslayout.num_fpga - 1):
                if i == j:
                    core_idx += 1
                if j < i:
                    if_idx = i - 1
                else:
                    if_idx = i
                # print("Connecting core {} out {} to core {} in {}".format(i, j, core_idx, if_idx))
                self.comb += self.cores[i].network.external_network_interface_out[j].connect(self.cores[core_idx].network.external_network_interface_in[if_idx])
                core_idx += 1


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

class AllInOneTop(Module):
    def __init__(self, config):
        self.submodules.uncore = AllInOneUnCore(config)

        self.submodules.platform = config.platform

        hmc_perf_counters = [Signal(32) for _ in range(2*9)]
        for i in range(9):
            port = self.platform.picoHMCports[i]
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
                for i in range(config.addresslayout.num_pe_per_fpga):
                    status_regs.extend([
                        core.apply[i].level
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

        self.bus = self.platform.getBus()

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




class UnCore(Module):
    def __init__(self, config, fpga_id):
        self.submodules.cores = [Core(config, fpga_id)]

        self.start = Signal()

        self.done = self.cores[0].done
        self.kernel_error = self.cores[0].kernel_error
        self.deadlock = self.cores[0].deadlock
        self.global_inactive = self.cores[0].global_inactive
        self.total_num_messages = self.cores[0].total_num_messages
        self.cycle_count = self.cores[0].cycle_count

        self.num_messages_to = [Signal(32) for _ in range(config.addresslayout.num_fpga - 1)]
        self.num_messages_from = [Signal(32) for _ in range(config.addresslayout.num_fpga - 1)]
        # self.out_fifo_in = [Signal(32) for _ in range(config.addresslayout.num_fpga - 1)]
        # self.in_fifo_in = [Signal(32) for _ in range(config.addresslayout.num_fpga - 1)]
        # self.out_fifo_out = [Signal(32) for _ in range(config.addresslayout.num_fpga - 1)]
        # self.in_fifo_out = [Signal(32) for _ in range(config.addresslayout.num_fpga - 1)]

        msg_recvd_sys = Signal()
        self.comb += self.cores[0].start.eq(self.start | msg_recvd_sys)

        msg_len = len(self.cores[0].network.external_network_interface_out[0].msg.raw_bits())

        self.submodules.in_fifo = [ClockDomainsRenamer({"write":"stream", "read":"sys"}) (AsyncFIFO(width=msg_len, depth=64)) for j in range(config.addresslayout.num_fpga - 1)]
        self.submodules.out_fifo = [ClockDomainsRenamer({"write":"sys", "read":"stream"}) (AsyncFIFO(width=msg_len, depth=64)) for j in range(config.addresslayout.num_fpga - 1)]
        # self.submodules.in_fifo = [ClockDomainsRenamer("stream")(SyncFIFO(width=msg_len, depth=64)) for j in range(config.addresslayout.num_fpga - 1)]
        # self.submodules.out_fifo = [ClockDomainsRenamer("stream")(SyncFIFO(width=msg_len, depth=64)) for j in range(config.addresslayout.num_fpga - 1)]

        rx_valids = []
        for j in range(config.addresslayout.num_fpga - 1):
            rx, tx = config.platform[fpga_id].getStreamPair()

            assert msg_len <= len(tx.data)

            self.comb += [
                self.out_fifo[j].din.eq(self.cores[0].network.external_network_interface_out[j].msg.raw_bits()),
                self.out_fifo[j].we.eq(self.cores[0].network.external_network_interface_out[j].valid),
                self.cores[0].network.external_network_interface_out[j].ack.eq(self.out_fifo[j].writable),
                tx.data.eq(self.out_fifo[j].dout),
                tx.valid.eq(self.out_fifo[j].readable),
                self.out_fifo[j].re.eq(tx.rdy),
                self.in_fifo[j].din.eq(rx.data),
                self.in_fifo[j].we.eq(rx.valid),
                rx.rdy.eq(self.in_fifo[j].writable),
                self.cores[0].network.external_network_interface_in[j].msg.raw_bits().eq(self.in_fifo[j].dout),
                self.cores[0].network.external_network_interface_in[j].valid.eq(self.in_fifo[j].readable),
                self.in_fifo[j].re.eq(self.cores[0].network.external_network_interface_in[j].ack)
            ]

            self.sync.stream += [
                # If(self.in_fifo[j].readable & self.in_fifo[j].re,
                #     self.in_fifo_out[j].eq(self.in_fifo_out[j] + 1)
                # ),
                # If(self.in_fifo[j].writable & self.in_fifo[j].we,
                #     self.in_fifo_in[j].eq(self.in_fifo_in[j] + 1)
                # ),
                # If(self.out_fifo[j].readable & self.out_fifo[j].re,
                #     self.out_fifo_out[j].eq(self.out_fifo_out[j] + 1)
                # ),
                # If(self.out_fifo[j].writable & self.out_fifo[j].we,
                #     self.out_fifo_in[j].eq(self.out_fifo_in[j] + 1)
                # ),
                If(rx.rdy & rx.valid,
                    self.num_messages_from[j].eq(self.num_messages_from[j] + 1)
                ),
                If(tx.rdy & tx.valid,
                    self.num_messages_to[j].eq(self.num_messages_from[j] + 1)
                )
            ]

            rx_valids.append(rx.valid)

        msg_recvd = Signal()
        self.sync.stream += If(reduce(or_, rx_valids),
            msg_recvd.eq(1)
        )
        self.specials += MultiReg(msg_recvd, msg_recvd_sys, odomain="sys")



class Top(Module):
    def __init__(self, config, fpga_id):
        self.submodules.uncore = UnCore(config, fpga_id)

        self.submodules.platform = config.platform[fpga_id]

        hmc_perf_counters = [Signal(32) for _ in range(2*9)]
        for i in range(9):
            port = self.platform.picoHMCports[i]
            self.sync += [
                If(port.cmd_valid & port.cmd_ready, hmc_perf_counters[i].eq(hmc_perf_counters[i]+1)),
                If(port.rd_data_valid & ~port.dinv, hmc_perf_counters[i+9].eq(hmc_perf_counters[i+9]+1))
            ]

        hmc_perf_counters_pico = [Signal(32) for _ in hmc_perf_counters]
        for i in range(len(hmc_perf_counters)):
            self.specials += MultiReg(hmc_perf_counters[i], hmc_perf_counters_pico[i], odomain="bus")

        status_regs = []
        for core in self.uncore.cores:
            for i in range(config.addresslayout.num_pe_per_fpga):
                status_regs.extend([
                    # core.apply[i].barrierdistributor.total_num_updates,
                    # core.scatter[i].barrierdistributor.total_num_messages_in,
                    # core.scatter[i].barrierdistributor.total_num_messages,
                    core.apply[i].level,
                    #core.apply[i].gatherapplykernel.num_triangles,
                    # core.scatter[i].get_neighbors.num_updates_accepted,
                    # *core.network.num_messages_to,
                    # *self.uncore.num_messages_to,
                    # *self.uncore.num_messages_from,
                    # *self.uncore.out_fifo_in,
                    # *self.uncore.out_fifo_out,
                    # *[f.level for f in self.uncore.out_fifo],
                    # *[Cat(f.readable, f.re, f.writable, f.we) for f in self.uncore.out_fifo],
                    # *core.network.num_messages_from,
                    # *self.uncore.in_fifo_in,
                    # *self.uncore.in_fifo_out,
                    # *[f.level for f in self.uncore.in_fifo],
                    # *[Cat(f.readable, f.re, f.writable, f.we) for f in self.uncore.in_fifo],
                    #core.apply[i].outfifo.max_level,
                    # *core.scatter[i].barrierdistributor.prev_num_msgs_since_last_barrier,
                    # Cat(core.scatter[i].network_interface.valid, core.scatter[i].network_interface.ack, core.scatter[i].network_interface.msg.barrier, core.scatter[i].network_interface.msg.roundpar),
                    # Cat(core.apply[i].apply_interface.valid, core.apply[i].apply_interface.ack, core.apply[i].apply_interface.msg.barrier, core.apply[i].apply_interface.msg.roundpar),
                    # Cat(core.network.arbiter[i].barriercounter.apply_interface_in.valid, core.network.arbiter[i].barriercounter.apply_interface_in.ack, core.network.arbiter[i].barriercounter.apply_interface_in.msg.barrier, core.network.arbiter[i].barriercounter.apply_interface_in.msg.roundpar),
                    # Cat(core.network.arbiter[i].barriercounter.apply_interface_out.valid, core.network.arbiter[i].barriercounter.apply_interface_out.ack, core.network.arbiter[i].barriercounter.apply_interface_out.msg.barrier, core.network.arbiter[i].barriercounter.apply_interface_out.msg.roundpar),
                    # *core.network.bc[i].num_from_pe,
                    # *core.network.bc[i].num_expected_from_pe,
                    # Cat(*core.network.bc[i].barrier_from_pe),
                    # core.network.bc[i].round_accepting
                ])

        # if config.memtype == "HMC" or config.memtype == "HMCO":
        #     status_regs.extend([sr for core in self.uncore.cores for n in core.scatter for sr in (n.get_neighbors.num_requests_accepted, n.get_neighbors.num_hmc_commands_issued, n.get_neighbors.num_hmc_responses, n.get_neighbors.num_hmc_commands_retired)])

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

        self.bus = self.platform.getBus()

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

def export_one(config, filename='top'):
    logger = logging.getLogger('config')
    config.platform = PicoPlatform(0 if config.memtype == "BRAM" else config.addresslayout.num_pe_per_fpga, create_hmc_ios=True, bus_width=32, stream_width=128)

    m = Top(config)
    logger.info("Exporting design to file {}".format(filename + '.v'))

    so = dict(migen.build.xilinx.common.xilinx_special_overrides)
    verilog.convert(m,
                    name=filename,
                    ios=config.platform.get_ios(),
                    special_overrides=so,
                    create_clock_domains=False
                    ).write(filename + '.v')
    if not config.memtype == "BRAM":
        export_data(config.adj_val, "adj_val.data")


def export(config, filename='top'):
    logger = logging.getLogger('config')
    config.platform = [PicoPlatform(config.addresslayout.num_pe_per_fpga, create_hmc_ios=True, bus_width=32, stream_width=128) for _ in range(config.addresslayout.num_fpga)]

    m = [Top(config, i) for i in range(config.addresslayout.num_fpga)]

    logger.info("Exporting design to files {0}[0-{1}]/{0}.v".format(filename, config.addresslayout.num_fpga - 1))

    for i in range(config.addresslayout.num_fpga):
        iname = filename + "_" + str(i)
        os.makedirs(iname, exist_ok=True)
        with cd(iname):
            verilog.convert(m[i],
                            name=filename,
                            ios=config.platform[i].get_ios()
                            ).write(filename + ".v")
    if not config.memtype == "BRAM":
        export_data(config.adj_val, "adj_val.data", backup=config.alt_adj_val_data_name)

def sim(config):
    config.platform = PicoPlatform(config.addresslayout.num_pe, bus_width=32, init=(config.adj_val if config.memtype != "BRAM" else []))
    tb = AllInOneUnCore(config)
    tb.submodules += config.platform

    generators = config.platform.getSimGenerators()

    generators["sys"].extend([core.gen_barrier_monitor(tb) for core in tb.cores])
    generators["sys"].extend(get_simulators(tb, 'gen_selfcheck', tb))
    generators["sys"].extend(get_simulators(tb, 'gen_simulation', tb))

    # generators.extend([a.gen_stats(tb) for a in tb.apply])
    # generators.extend([tb.gen_network_stats()])
    run_simulation(tb, generators, clocks={"sys": 10, "bus": 480, "stream": 8}, vcd_name="{}.vcd".format(config.vcdname))


def main():
    args, config = init_parse(inverted=True, cmd_choices=("sim", "export", "export_one"))

    logger = logging.getLogger('config')

    if args.command=='sim':
        logger.info("Starting Simulation")
        sim(config)
    elif args.command=='export':
        filename = "top"
        if args.output:
            filename = args.output
        export(config, filename=filename)
    elif args.command=='export_one':
        filename = "top"
        if args.output:
            filename = args.output
        export_one(config, filename=filename)
    else:
        logger.error("Unrecognized command")
        raise NotImplementedError

if __name__ == '__main__':
    main()
