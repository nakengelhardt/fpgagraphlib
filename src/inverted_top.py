from migen.fhdl import verilog

from migen import *
from tbsupport import *

import logging
from contextlib import ExitStack

from functools import reduce
from operator import and_

from core_init import init_parse
from util.recordfifo import RecordFIFO
from core_interfaces import Message

from core_interfaces import *
from inverted_network import UpdateNetwork
from inverted_apply import Apply
from inverted_scatter import Scatter
from core_bramif import *

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

        # # I/O interface
        # internal_mem_ports = [a.external_wr_port for a in self.apply]
        # internal_mem_ports.extend([s.wr_port_idx for s in self.scatter])
        # internal_mem_ports.extend([s.get_neighbors.wr_port_val for s in self.scatter])
        # self.submodules.bramio = BRAMIO(start_addr=config.start_addr, endpoints=internal_mem_ports)
        # self.init_complete = Signal()

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

    def gen_simulation(self, tb):
        word_offset = self.bramio.word_offset
        addr_spacing = self.bramio.addr_spacing
        start_addr = self.config.start_addr
        for pe_id in range(self.config.addresslayout.num_pe):
            if self.config.init_nodedata:
                for addr, data in enumerate(self.config.init_nodedata[pe_id]):
                    yield from self.bramio.axi_port.write(adr=start_addr + (addr << word_offset), wdata=data)
            start_addr += addr_spacing
        for pe_id in range(self.config.addresslayout.num_pe):
            for addr, (index, length) in enumerate(self.config.adj_idx[pe_id]):
                data = convert_record_to_int([("index", self.config.addresslayout.edgeidsize), ("length", self.config.addresslayout.edgeidsize)], index=index, length=length)
                yield from self.bramio.axi_port.write(adr=start_addr + (addr << word_offset), wdata=data)
            start_addr += addr_spacing
        for pe_id in range(self.config.addresslayout.num_pe):
            for addr, data in enumerate(self.config.adj_val[pe_id]):
                yield from self.bramio.axi_port.write(adr=start_addr + (addr << word_offset), wdata=data)
            start_addr += addr_spacing
        yield self.init_complete.eq(1)
        while not (yield tb.global_inactive):
            yield
        start_addr = self.config.start_addr
        for pe_id in range(self.config.addresslayout.num_pe):
            num_valid_nodes = tb.config.addresslayout.max_node_per_pe(tb.config.adj_dict)[pe_id] + 1
            for addr in range(num_valid_nodes):
                data = (yield from self.bramio.axi_port.read(adr=start_addr + (addr << word_offset)))
                r = convert_int_to_record(data, self.config.addresslayout.node_storage_layout)
                vertexid = self.config.addresslayout.global_adr(pe_id, addr)
                if vertexid != 0:
                    print("Data of Vertex {}:\t {}".format(self.config.graph.node[vertexid]["origin"], [(f[0], r[f[0]]) for f in self.config.addresslayout.node_storage_layout]))
            start_addr += addr_spacing

class UnCore(Module):
    def __init__(self, config):
        self.config = config
        num_pe = config.addresslayout.num_pe

        self.submodules.cores = [Core(config)]

        self.global_inactive = Signal()
        self.comb += self.global_inactive.eq(self.cores[0].global_inactive)

        start_message = self.cores[0].start_message
        injected = [Signal() for i in range(num_pe)]


        self.start = Signal()
        init = Signal()
        self.done = Signal()
        self.cycle_count = Signal(32)
        # self.total_num_messages = self.cores[0].total_num_messages

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

    def gen_simulation(self, tb):
        while not (yield self.cores[0].init_complete):
            yield
        yield self.start.eq(1)
        yield

def sim(config):

    tb = UnCore(config)

    generators = []

    for core in tb.cores:
        generators.extend([core.gen_barrier_monitor(tb)])
        generators.extend([core.bramio.axi_port.gen_radr(), core.bramio.axi_port.gen_rdata(), core.bramio.axi_port.gen_wadr(), core.bramio.axi_port.gen_wdata(), core.bramio.axi_port.gen_wresp()])

    generators.extend(get_simulators(tb, 'gen_selfcheck', tb))
    generators.extend(get_simulators(tb, 'gen_simulation', tb))

    run_simulation(tb, generators, vcd_name="{}.vcd".format(config.vcdname))

def export(config, filename='top.v'):

    m = UnCore(config)
    m.clock_domains.cd_sys = ClockDomain(reset_less=True)

    verilog.convert(m,
                    name="top",
                    ios={m.start, m.done, m.cycle_count, m.cd_sys.clk}
                    ).write(filename)

def main():
    args, config = init_parse(inverted=True)

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
