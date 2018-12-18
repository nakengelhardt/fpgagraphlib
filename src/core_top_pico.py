from migen import *
from tbsupport import *
from migen.fhdl import verilog
import migen.build.xilinx.common
from migen.genlib.resetsync import AsyncResetSynchronizer
from migen.genlib.cdc import *
from migen.genlib.fifo import AsyncFIFO

import logging

from functools import reduce
from operator import or_, and_

from pico import PicoPlatform

from core_init import init_parse

from recordfifo import RecordFIFO
from core_interfaces import Message
from fifo_network import Network, MultiNetwork
from core_apply import Apply
from core_scatter import Scatter

class Core(Module):
    def __init__(self, config, fpga_id):
        self.config = config
        self.pe_start = pe_start = fpga_id*config.addresslayout.num_pe_per_fpga
        self.pe_end = pe_end = min((fpga_id+1)*config.addresslayout.num_pe_per_fpga, config.addresslayout.num_pe)
        num_local_pe = pe_end - pe_start

        if config.has_edgedata:
            init_edgedata = config.init_edgedata
        else:
            init_edgedata = [None for _ in range(num_local_pe)]

        if config.addresslayout.num_fpga == 1:
            self.submodules.network = Network(config)
        else:
            self.submodules.network = MultiNetwork(config, fpga_id)

        self.submodules.apply = [Apply(config, i) for i in range(pe_start, pe_end)]


        if config.use_hmc:
            self.submodules.scatter = [Scatter(i, config, hmc_port=config.platform[fpga_id].getHMCPort(i % config.addresslayout.num_pe_per_fpga)) for i in range(pe_start, pe_end)]
        else:
            self.submodules.scatter = [Scatter(i, config) for i in range(pe_start, pe_end)]

        # connect within PEs
        self.comb += [self.apply[i].scatter_interface.connect(self.scatter[i].scatter_interface) for i in range(num_local_pe)]

        # connect to network
        self.comb += [self.network.apply_interface[i].connect(self.apply[i].apply_interface) for i in range(num_local_pe)]
        self.comb += [self.scatter[i].network_interface.connect(self.network.network_interface[i]) for i in range(num_local_pe)]

        # state of calculation
        self.global_inactive = Signal()
        self.comb += self.global_inactive.eq(reduce(and_, [pe.inactive for pe in self.apply]))

        self.kernel_error = Signal()
        self.comb += self.kernel_error.eq(reduce(or_, [pe.gatherapplykernel.kernel_error for pe in self.apply]))

        self.deadlock = Signal()
        self.comb += self.deadlock.eq(reduce(or_, [pe.deadlock for pe in self.apply]))

        self.total_num_messages = Signal(32)
        self.comb += [
            self.total_num_messages.eq(sum(scatter.barrierdistributor.total_num_messages for scatter in self.scatter))
        ]

        start_message = [a.start_message for a in self.network.arbiter]
        assert len(start_message) == num_local_pe

        injected = [Signal() for i in range(num_local_pe)]

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

        for i in range(num_local_pe):
            self.comb += [
                start_message[i].select.eq(init),
                start_message[i].msg.barrier.eq(1),
                start_message[i].msg.roundpar.eq(config.addresslayout.num_channels-1),
                start_message[i].valid.eq(~injected[i])
            ]

        self.sync += [
            [If(start_message[i].ack, injected[i].eq(1)) for i in range(num_local_pe)],
            If(~reduce(and_, injected),
                self.cycle_count.eq(0)
            ).Elif(~self.global_inactive,
                self.cycle_count.eq(self.cycle_count + 1)
            )
        ]

    def gen_barrier_monitor(self, tb):
        logger = logging.getLogger('sim.barriermonitor')
        num_pe = self.pe_end - self.pe_start
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
                if ((yield self.apply[i].gatherapplykernel.valid_in)
                    and (yield self.apply[i].gatherapplykernel.ready)):
                    if (yield self.apply[i].level) % self.config.addresslayout.num_channels != (yield self.apply[i].gatherapplykernel.round_in):
                        logger.warning("{}: received message's parity ({}) does not match current round ({})".format(num_cycles, (yield self.apply[i].gatherapplykernel.round_in), (yield self.apply[i].level)))
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
    def __init__(self, config, fpga_id):
        self.config = config

        self.submodules.cores = [Core(config, fpga_id)]

        self.global_inactive = self.cores[0].global_inactive
        self.kernel_error = self.cores[0].kernel_error
        self.deadlock = self.cores[0].deadlock
        self.total_num_messages = self.cores[0].total_num_messages
        self.cycle_count = self.cores[0].cycle_count
        self.start = self.cores[0].start
        self.done = self.cores[0].done

        self.num_messages_to = [Signal(32) for _ in range(config.addresslayout.num_fpga - 1)]
        self.num_messages_from = [Signal(32) for _ in range(config.addresslayout.num_fpga - 1)]

        msg_recvd_sys = Signal()
        self.comb += self.cores[0].start.eq(self.start | msg_recvd_sys)

        if config.addresslayout.num_fpga > 1:
            msg_len = len(self.cores[0].network.external_network_interface_out[0].msg.raw_bits())

            self.submodules.in_fifo = [ClockDomainsRenamer({"write":"stream", "read":"sys"}) (AsyncFIFO(width=msg_len, depth=64)) for j in range(config.addresslayout.num_fpga - 1)]
            self.submodules.out_fifo = [ClockDomainsRenamer({"write":"sys", "read":"stream"}) (AsyncFIFO(width=msg_len, depth=64)) for j in range(config.addresslayout.num_fpga - 1)]

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
                    If(rx.rdy & rx.valid,
                        self.num_messages_from[j].eq(self.num_messages_from[j] + 1)
                    ),
                    If(tx.rdy & tx.valid,
                        self.num_messages_to[j].eq(self.num_messages_from[j] + 1)
                    )
                ]

                rx_valids.append(rx.valid)

            msg_recvd = Signal()
            self.sync.stream += If(reduce(or_, rx_valids, 0),
                msg_recvd.eq(1)
            )
            self.specials += MultiReg(msg_recvd, msg_recvd_sys, odomain="sys")

class Top(Module):
    def __init__(self, config, fpga_id):
        self.submodules.uncore = UnCore(config, fpga_id)

        self.submodules.platform = config.platform[fpga_id]

        if not config.use_hmc:
            for port in self.platform.picoHMCports:
                for field, _, dir in port.layout:
                    if field != "clk" and dir == DIR_M_TO_S:
                        s = getattr(port, field)
                        self.comb += s.eq(0)

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

        if config.use_hmc:
            status_regs = [sr for core in self.uncore.cores for n in core.scatter for sr in (n.get_neighbors.num_requests_accepted, n.get_neighbors.num_hmc_commands_issued, n.get_neighbors.num_hmc_responses, n.get_neighbors.num_hmc_commands_retired)]
        else:
            status_regs = []

        for core in self.uncore.cores:
            for i in range(config.addresslayout.num_pe_per_fpga):
                status_regs.extend([
                    # core.scatter[i].barrierdistributor.total_num_messages_in,
                    core.scatter[i].barrierdistributor.total_num_messages,
                    core.apply[i].level,
                    #core.apply[i].gatherapplykernel.num_triangles,
                    #core.scatter[i].get_neighbors.num_neighbors_issued,
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

class SimTB(Module):
    def __init__(self, config):
        self.config = config

        self.submodules.cores = [Core(config, i) for i in range(config.addresslayout.num_fpga)]

        self.global_inactive = reduce(and_, (core.global_inactive for core in self.cores))
        self.kernel_error = reduce(and_, [core.kernel_error for core in self.cores])
        self.deadlock = reduce(and_, [core.deadlock for core in self.cores])
        self.total_num_messages = sum(core.total_num_messages for core in self.cores)
        self.start = Signal()

        self.comb += [core.start.eq(self.start) for core in self.cores]

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

def export(config, filename='top'):
    logger = logging.getLogger('config')
    config.platform = [PicoPlatform(config.addresslayout.num_pe, bus_width=32, stream_width=128) for _ in range(config.addresslayout.num_fpga)]

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
    if config.use_hmc:
        with open("adj_val.data", 'wb') as f:
            for x in config.adj_val:
                f.write(struct.pack('=I', x))

def sim(config):
    config.platform = [PicoPlatform(config.addresslayout.num_pe, bus_width=32, stream_width=128, init=(config.adj_val if config.use_hmc else []))]
    tb = SimTB(config)
    tb.submodules += config.platform

    generators = config.platform[0].getSimGenerators()
    for i in range(1, len(config.platform)):
        g = config.platform[i].getSimGenerators()
        for cd in generators:
            generators[cd].extend(g[cd])

    generators["sys"].extend([core.gen_barrier_monitor(tb) for core in tb.cores])
    generators["sys"].extend(get_simulators(tb, 'gen_selfcheck', tb))
    generators["sys"].extend(get_simulators(tb, 'gen_simulation', tb))

    # generators.extend([a.gen_stats(tb) for a in tb.apply])
    # generators.extend([tb.gen_network_stats()])
    run_simulation(tb, generators, clocks={"sys": 10, "bus": 480, "stream": 8}, vcd_name="{}.vcd".format(config.vcdname))


def main():
    args, config = init_parse(cmd_choices=("sim", "export", "export_one"))

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
