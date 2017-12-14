from migen.fhdl import verilog
from migen import *
from migen.genlib.roundrobin import *
from migen.genlib.cdc import *
from tbsupport import *

from functools import reduce
from operator import and_

import logging
import random
import os

from core_init import init_parse

from recordfifo import *
from core_interfaces import Message
from tkb_network import Network
from core_apply import Apply
from core_scatter import Scatter

class Core(Module):
    def __init__(self, config, pe_start, pe_end):
        self.config = config
        self.pe_start = pe_start

        num_local_pe = pe_end - pe_start
        num_pe = self.config.addresslayout.num_pe
        num_nodes_per_pe = self.config.addresslayout.num_nodes_per_pe

        num_nodes = len(config.adj_dict)

        if config.has_edgedata:
            init_edgedata = config.init_edgedata[pe_start:pe_end]
        else:
            init_edgedata = [None for _ in range(num_local_pe)]

        self.submodules.network = Network(config, pe_start, pe_end)
        self.submodules.apply = [Apply(config, i, config.init_nodedata[i] if config.init_nodedata else None) for i in range(pe_start, pe_end)]

        self.submodules.scatter = [Scatter(i, config, adj_mat=(config.adj_idx[i], config.adj_val[i]), edge_data=init_edgedata[i-pe_start]) for i in range(pe_start, pe_end)]

        # connect within PEs
        self.comb += [self.apply[i].scatter_interface.connect(self.scatter[i].scatter_interface) for i in range(num_local_pe)]

        # connect to network
        self.comb += [self.network.apply_interface[i].connect(self.apply[i].apply_interface) for i in range(num_local_pe)]
        self.comb += [self.scatter[i].network_interface.connect(self.network.network_interface[i]) for i in range(num_local_pe)]

        # state of calculation
        self.global_inactive = Signal()
        self.comb += self.global_inactive.eq(reduce(and_, [pe.inactive for pe in self.apply]))

        start_message = [a.start_message for a in self.network.arbiter]
        layout = Message(**config.addresslayout.get_params()).layout
        initdata = []
        for i in range(pe_start, pe_end):
            initdata.append([convert_record_to_int(layout, barrier=0, roundpar=config.addresslayout.num_channels-1, dest_id=msg['dest_id'], sender=msg['sender'], payload=msg['payload'], halt=0) for msg in sorted(config.init_messages[i], key=lambda x: x["dest_id"])])
        for i in initdata:
            i.append(convert_record_to_int(layout, barrier=1, roundpar=config.addresslayout.num_channels-1))
        initfifos = [RecordFIFO(layout=layout, depth=len(ini)+1, init=ini, name="initfifo_"+str(i)) for i, ini in enumerate(initdata)]

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

        for i, initfifo in enumerate(initfifos):
            self.comb += [
                start_message[i].select.eq(init),
                start_message[i].msg.eq(initfifo.dout),
                start_message[i].valid.eq(initfifo.readable),
                initfifo.re.eq(start_message[i].ack)
            ]

        self.sync += [
            If(init,
                self.cycle_count.eq(0)
            ).Elif(~self.global_inactive,
                self.cycle_count.eq(self.cycle_count + 1)
            )
        ]

    def gen_barrier_monitor(self, tb):
        logger = logging.getLogger('simulation.barriermonitor')
        num_pe = self.config.addresslayout.num_pe
        num_local_pe = len(self.apply)

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

class UnCore(Module):
    def __init__(self, config):
        self.config = config
        assert(config.addresslayout.num_fpga <= 2)
        self.submodules.cores = [Core(config, i*config.addresslayout.num_pe_per_fpga, min((i+1)*config.addresslayout.num_pe_per_fpga, config.addresslayout.num_pe)) for i in range(config.addresslayout.num_fpga)]

        self.global_inactive = Signal()
        self.comb += self.global_inactive.eq(reduce(and_, [core.global_inactive for core in self.cores]))

        self.comb += [
            self.cores[0].network.message_in_data.eq(self.cores[1].network.message_out_data),
            self.cores[0].network.message_in_valid.eq(self.cores[1].network.message_out_valid),
            self.cores[1].network.message_out_ack.eq(self.cores[0].network.message_in_ack),

            self.cores[1].network.message_in_data.eq(self.cores[0].network.message_out_data),
            self.cores[1].network.message_in_valid.eq(self.cores[0].network.message_out_valid),
            self.cores[0].network.message_out_ack.eq(self.cores[1].network.message_in_ack),

            self.cores[0].network.nrs.receive_barrier.eq(self.cores[1].network.nrs.send_barrier),
            self.cores[1].network.nrs.send_barrier_ack.eq(self.cores[0].network.nrs.receive_barrier_ack),
            self.cores[1].network.nrs.receive_barrier.eq(self.cores[0].network.nrs.send_barrier),
            self.cores[0].network.nrs.send_barrier_ack.eq(self.cores[1].network.nrs.receive_barrier_ack),
        ]

        self.start = Signal()
        self.done = Signal()
        self.cycle_count = Signal(32)

        self.comb += [
            [core.start.eq(self.start) for core in self.cores],
            self.done.eq(reduce(and_, [core.done for core in self.cores])),
            self.cycle_count.eq(self.cores[0].cycle_count)
        ]

    def gen_simulation(self, tb):
        yield self.start.eq(1)

def sim(config):
    tb = UnCore(config)

    generators = []

    for core in tb.cores:
        generators.extend([core.gen_barrier_monitor(tb)])

    generators.extend(get_simulators(tb, 'gen_selfcheck', tb))
    generators.extend(get_simulators(tb, 'gen_simulation', tb))

    run_simulation(tb, generators, vcd_name="tb.vcd")

def export_one(config, filename='top.v'):

    m = UnCore(config)

    verilog.convert(m,
                    name="top",
                    ios={m.start, m.done, m.cycle_count}
                    ).write(filename)

def export(config, filename='top'):

    m = [Core(config, i*config.addresslayout.num_pe_per_fpga, min((i+1)*config.addresslayout.num_pe_per_fpga, config.addresslayout.num_pe)) for i in range(config.addresslayout.num_fpga)]

    for i in range(config.addresslayout.num_fpga):
        iname = filename + "_" + str(i)
        os.makedirs(iname, exist_ok=True)
        with cd(iname):
            ios={m[i].start, m[i].done, m[i].cycle_count}
            ios |= m[i].network.ios
            verilog.convert(m[i],
                            name="top",
                            ios=ios
                            ).write(iname + ".v")

def main():
    args, config = init_parse()

    logger = logging.getLogger('config')

    if args.command=='sim':
        logger.info("Starting Simulation")
        sim(config)
    if args.command=='export_one':
        filename = "top.v"
        if args.output:
            filename = args.output
        logger.info("Exporting design to file {}".format(filename))
        export_one(config, filename=filename)
    if args.command=='export':
        filename = "top"
        if args.output:
            filename = args.output
        logger.info("Exporting design to files {}_[0-{}].v".format(filename, config.addresslayout.num_fpga-1))
        export(config, filename=filename)

if __name__ == '__main__':
    main()
