from migen.fhdl import verilog

from migen import *
from tbsupport import *
from migen.genlib.roundrobin import *

import logging
from contextlib import ExitStack

from functools import reduce
from operator import and_, or_

from core_init import init_parse
from recordfifo import RecordFIFO
from core_interfaces import Message

from core_interfaces import Message
from fifo_network import Network
from core_apply import Apply
from core_scatter import Scatter
from core_ddr import *
from core_bramif import *

class Core(Module):
    def __init__(self, config):
        self.config = config
        num_pe = self.config.addresslayout.num_pe

        if config.use_ddr and config.has_edgedata:
            raise NotImplementedError()

        self.submodules.network = Network(config)
        self.submodules.apply = [Apply(config, i) for i in range(num_pe)]

        self.submodules.portsharer = DDRPortSharer(config=config, num_ports=num_pe)

        self.submodules.scatter = [Scatter(i, config, hmc_port=self.portsharer.get_port(i)) for i in range(num_pe)]

        # connect within PEs
        self.comb += [self.apply[i].scatter_interface.connect(self.scatter[i].scatter_interface) for i in range(num_pe)]

        # connect to network
        self.comb += [self.network.apply_interface[i].connect(self.apply[i].apply_interface) for i in range(num_pe)]
        self.comb += [self.scatter[i].network_interface.connect(self.network.network_interface[i]) for i in range(num_pe)]

        # state of calculation
        self.global_inactive = Signal()
        self.comb += self.global_inactive.eq(reduce(and_, [pe.inactive for pe in self.apply]))
        self.total_num_messages = Signal(32)
        self.comb += [
            self.total_num_messages.eq(sum(scatter.barrierdistributor.total_num_messages for scatter in self.scatter))
        ]

        # I/O interface
        internal_mem_ports = [a.external_wr_port for a in self.apply]
        internal_mem_ports.extend([s.wr_port_idx for s in self.scatter])
        if not config.use_ddr:
            internal_mem_ports.extend([s.get_neighbors.wr_port_val for s in self.scatter])
        self.submodules.bramio = BRAMIO(start_addr=config.start_addr, endpoints=internal_mem_ports)
        self.init_complete = Signal()

    def gen_barrier_monitor(self, tb):
        logger = logging.getLogger('simulation.barriermonitor')
        num_pe = self.config.addresslayout.num_pe

        num_cycles = 0
        while not (yield tb.global_inactive):
            num_cycles += 1
            for a in self.apply:
                if ((yield a.apply_interface.valid) and (yield a.apply_interface.ack)):
                    if (yield a.apply_interface.msg.barrier):
                        logger.debug(str(num_cycles) + ": Barrier enters Apply on PE " + str(a.pe_id))
                if (yield a.gatherkernel.valid_in) and (yield a.gatherkernel.ready):
                    if ((yield a.level) - 1) % self.config.addresslayout.num_channels != (yield a.roundpar):
                        logger.warning("{}: received message's parity ({}) does not match current round ({})".format(num_cycles, (yield a.roundpar), (yield a.level)))
                if ((yield a.scatter_interface.barrier) and (yield a.scatter_interface.valid) and (yield a.scatter_interface.ack)):
                    logger.debug(str(num_cycles) + ": Barrier exits Apply on PE " + str(a.pe_id))
            for s in self.scatter:
                if ((yield s.scatter_interface.valid) and (yield s.scatter_interface.ack)):
                    if (yield s.scatter_interface.barrier):
                        logger.debug(str(num_cycles) + ": Barrier enters Scatter on PE " + str(s.pe_id))
                if ((yield s.barrierdistributor.network_interface_in.valid) and (yield s.barrierdistributor.network_interface_in.ack)):
                    if (yield s.barrierdistributor.network_interface_in.msg.barrier):
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
        if not self.config.use_ddr:
            for pe_id in range(self.config.addresslayout.num_pe):
                for addr, data in enumerate(self.config.adj_val[pe_id]):
                    yield from self.bramio.axi_port.write(adr=start_addr + (addr << word_offset), wdata=data)
                start_addr += addr_spacing
        yield self.init_complete.eq(1)
        while not (yield tb.global_inactive):
            yield
        start_addr = self.config.start_addr
        for pe_id in range(self.config.addresslayout.num_pe):
            for addr in range(len(self.config.adj_idx[pe_id])):
                data = (yield from self.bramio.axi_port.read(adr=start_addr + (addr << word_offset)))
                r = convert_int_to_record(data, self.config.addresslayout.node_storage_layout)
                vertexid = self.config.addresslayout.global_adr(pe_id, addr)
                if vertexid != 0:
                    print("Data of Vertex {}:\t {}".format(vertexid, [(f[0], r[f[0]]) for f in self.config.addresslayout.node_storage_layout]))
            start_addr += addr_spacing


class UnCore(Module):
    def __init__(self, config):
        self.config = config
        num_pe = config.addresslayout.num_pe

        self.submodules.cores = [Core(config)]

        self.global_inactive = Signal()
        self.comb += self.global_inactive.eq(self.cores[0].global_inactive)

        start_message = [a.start_message for core in self.cores for a in core.network.arbiter]
        layout = Message(**config.addresslayout.get_params()).layout
        initdata = [[convert_record_to_int(layout, barrier=0, roundpar=config.addresslayout.num_channels-1, dest_id=msg['dest_id'], sender=msg['sender'], payload=msg['payload'], halt=0) for msg in sorted(init_message, key=lambda x: x["dest_id"])] for init_message in config.init_messages]
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
        self.total_num_messages = self.cores[0].total_num_messages

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
            If(~self.start,
                self.cycle_count.eq(0)
            ).Elif(~self.global_inactive,
                self.cycle_count.eq(self.cycle_count + 1)
            )
        ]

        self.kernel_error = Signal()

        self.comb += self.kernel_error.eq(reduce(or_, (a.applykernel.kernel_error for a in self.cores[0].apply)))

    def gen_simulation(self, tb):
        while not (yield self.cores[0].init_complete):
            yield
        yield self.start.eq(1)
        yield

def sim(config):

    tb = UnCore(config)

    if len(config.adj_dict) < 64:
        print(config.adj_dict)

    generators = []

    for core in tb.cores:
        generators.extend([core.gen_barrier_monitor(tb)])
        generators.extend([core.bramio.axi_port.gen_radr(), core.bramio.axi_port.gen_rdata(), core.bramio.axi_port.gen_wadr(), core.bramio.axi_port.gen_wdata(), core.bramio.axi_port.gen_wresp()])

    generators.extend(get_simulators(tb, 'gen_selfcheck', tb))
    generators.extend(get_simulators(tb, 'gen_simulation', tb))

    run_simulation(tb, generators, vcd_name="tb.vcd")

def export(config, filename='top.v'):

    m = UnCore(config)
    m.clock_domains.cd_sys = ClockDomain(reset_less=True)

    ios = {m.start, m.done, m.cycle_count, m.total_num_messages, m.cd_sys.clk, m.kernel_error}
    if config.use_ddr:
        ios |= m.cores[0].portsharer.get_ios()

    verilog.convert(m,
                    name="top",
                    ios=ios
                    ).write(filename)

    with open("address_mapping.txt", 'w') as adrmap:
        word_offset = m.cores[0].bramio.word_offset
        addr_spacing = m.cores[0].bramio.addr_spacing
        start_addr = m.cores[0].config.start_addr
        if config.init_nodedata:
            for pe_id, data in enumerate(config.init_nodedata):
                fname = "init_nodedata{}.data".format(pe_id)
                with open(fname, 'wb') as f:
                    adrmap.write("{}\t{}\n".format(hex(start_addr), fname))
                    for x in data:
                        f.write(struct.pack('=I', x))
                start_addr += addr_spacing
        else:
            start_addr += config.addresslayout.num_pe * addr_spacing
        for pe_id, adj_idx in enumerate(config.adj_idx):
            fname = "adj_idx{}.data".format(pe_id)
            with open(fname, 'wb') as f:
                adrmap.write("{}\t{}\n".format(hex(start_addr), fname))
                for index, length in adj_idx:
                    data = convert_record_to_int([("index", config.addresslayout.edgeidsize), ("length", config.addresslayout.edgeidsize)], index=index, length=length)
                    f.write(struct.pack('=I', data))
            start_addr += addr_spacing
        if config.use_ddr:
            with open("adj_val.data", 'wb') as f:
                adrmap.write("0x000000000\tadj_val.data\n")
                for x in config.adj_val:
                    f.write(struct.pack('=I', x))
        else:
            fname = "adj_val{}.data".format(pe_id)
            with open(fname, 'wb') as f:
                adrmap.write("{}\t{}\n".format(hex(start_addr), fname))
                for x in data:
                    f.write(struct.pack('=I', x))
            start_addr += addr_spacing

def export_fake(config, filename='top.v'):

    m = UnCore(config)
    m.clock_domains.cd_sys = ClockDomain(reset_less=True)

    m.cores[0].submodules += FakeDDR(config=config, port=m.cores[0].portsharer.real_port)

    real_port = Record(m.cores[0].portsharer.real_port.layout, name="real_port")

    ios = {m.start, m.done, m.cycle_count, m.total_num_messages, m.cd_sys.clk}
    ios |= set(real_port.flatten())

    if config.name == "pr":
        ios.add(m.kernel_error)

    verilog.convert(m,
                    name="top",
                    ios=ios
                    ).write(filename)

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
    if args.command=='export_fake':
        filename = "top.v"
        if args.output:
            filename = args.output
        logger.info("Exporting design to file {}".format(filename))
        export_fake(config, filename=filename)

if __name__ == '__main__':
    main()
