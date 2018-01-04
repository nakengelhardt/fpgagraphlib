from migen.fhdl import verilog

from migen import *
from tbsupport import *

import logging
from contextlib import ExitStack

from functools import reduce
from operator import and_

from core_init import init_parse
from recordfifo import RecordFIFO
from core_interfaces import Message

from core_interfaces import Message
from fifo_network import Network
from core_apply import Apply
from core_scatter import Scatter

_ddr_layout = [
                ("arid", "ID_WIDTH", DIR_M_TO_S),
                ("araddr", "ADDR_WIDTH", DIR_M_TO_S),
                ("arready", 1, DIR_S_TO_M),
                ("arvalid", 1, DIR_M_TO_S),
                ("rid", "ID_WIDTH", DIR_S_TO_M),
                ("rdata", "DATA_WIDTH", DIR_S_TO_M),
                ("rready", 1, DIR_M_TO_S),
                ("rvalid", 1, DIR_S_TO_M)
            ]

class Core(Module):
    def __init__(self, config):
        self.config = config
        num_pe = self.config.addresslayout.num_pe

        self.port = Record(set_layout_parameters(_ddr_layout, ID_WIDTH=4, ADDR_WIDTH=33, DATA_WIDTH=64*8))

        if config.has_edgedata:
            raise NotImplementedError()

        self.submodules.network = Network(config)
        self.submodules.apply = [Apply(config, i, config.init_nodedata[i] if config.init_nodedata else None) for i in range(num_pe)]

        self.submodules.scatter = [Scatter(i, config, adj_mat=(config.adj_idx[i], config.adj_val[i]), hmc_port=self.port) for i in range(num_pe)]

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

    @passive
    def gen_simulation(self, tb):
        logger = logging.getLogger("ddr_sim")
        edges_per_burst = len(self.port.rdata)//32
        burst_bytes = len(self.port.rdata)//8
        inflight_requests = []
        yield self.port.arready.eq(1)
        yield self.port.rvalid.eq(0)
        while True:
            if (yield self.port.rready):
                if inflight_requests: # and random.choice([True, False])
                    tag, addr = inflight_requests[0]
                    inflight_requests.pop(0)
                    logger.debug("Request: addr = {}, tag = {}".format(hex(addr), tag))
                    assert(addr % burst_bytes == 0)
                    idx = addr // 4
                    data = 0
                    for i in reversed(range(edges_per_burst)):
                        data = (data << 32) | self.config.adj_val[idx + i]
                    yield self.port.rdata.eq(data)
                    yield self.port.rid.eq(tag)
                    yield self.port.rvalid.eq(1)
                else:
                    yield self.port.rvalid.eq(0)
            yield
            if (yield self.port.arready) and (yield self.port.arvalid):
                inflight_requests.append(((yield self.port.arid), (yield self.port.araddr)))

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

    def gen_simulation(self, tb):
        yield self.start.eq(1)
        yield

def sim(config):

    tb = UnCore(config)

    generators = []

    for core in tb.cores:
        generators.extend([core.gen_barrier_monitor(tb)])

    generators.extend(get_simulators(tb, 'gen_selfcheck', tb))
    generators.extend(get_simulators(tb, 'gen_simulation', tb))

    run_simulation(tb, generators, vcd_name="tb.vcd")

def export(config, filename='top.v'):

    m = UnCore(config)
    m.clock_domains.cd_sys = ClockDomain(reset_less=True)

    ios = {m.start, m.done, m.cycle_count, m.total_num_messages, m.cd_sys.clk}
    ios |= set(m.cores[0].port.flatten())

    verilog.convert(m,
                    name="top",
                    ios=ios
                    ).write(filename)
    if config.use_ddr:
        with open("adj_val.data", 'wb') as f:
            for x in config.adj_val:
                f.write(struct.pack('=I', x))

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
