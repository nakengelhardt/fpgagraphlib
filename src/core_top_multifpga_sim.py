from migen.fhdl import verilog
import migen.build.xilinx.common

from migen import *
from tbsupport import *

from functools import reduce
from operator import and_

import logging
import random

from core_init import init_parse

from core_core_tb import Core

class SimTop(Module):
    def __init__(self, config):
        self.config = config
        self.submodules.cores = [Core(config, i*config.addresslayout.num_pe_per_fpga, min((i+1)*config.addresslayout.num_pe_per_fpga, config.addresslayout.num_pe)) for i in range(config.addresslayout.num_fpga)]

        self.global_inactive = Signal()
        self.comb += self.global_inactive.eq(reduce(and_, [core.global_inactive for core in self.cores]))

    @passive
    def gen_inter_fpga_connections(self):
        logger = logging.getLogger('simulation.extnet')
        dest_q = [[list() for _ in range(self.config.addresslayout.num_channels)] for _ in range(self.config.addresslayout.num_fpga)]
        num_pe_per_fpga = self.config.addresslayout.num_pe_per_fpga

        while(True):
            for core in range(self.config.addresslayout.num_fpga):
                for i in range(self.config.addresslayout.num_channels):
                    if len(dest_q[core][i]) > 0:
                        dest_pe, msg = dest_q[core][i][0]
                        (yield self.cores[core].network.external_network_interface_in[i].msg.raw_bits().eq(msg))
                        (yield self.cores[core].network.external_network_interface_in[i].dest_pe.eq(dest_pe))
                        (yield self.cores[core].network.external_network_interface_in[i].valid.eq(1))
                    else:
                        (yield self.cores[core].network.external_network_interface_in[i].valid.eq(0))

                    (yield self.cores[core].network.external_network_interface_out[i].ack.eq(random.choice([0,1]))) #TODO: random.choice([0,1])

            yield

            for core in range(self.config.addresslayout.num_fpga):
                for i in range(self.config.addresslayout.num_channels):
                    if (yield self.cores[core].network.external_network_interface_in[i].valid) and (yield self.cores[core].network.external_network_interface_in[i].ack):
                        logger.debug("OUT: Message to PE {} (FPGA {})".format(i, i//num_pe_per_fpga))
                        del dest_q[core][i][0]

                    if (yield self.cores[core].network.external_network_interface_out[i].valid) and (yield self.cores[core].network.external_network_interface_out[i].ack):
                        msg = (yield self.cores[core].network.external_network_interface_out[i].msg.raw_bits())
                        dest_pe = (yield self.cores[core].network.external_network_interface_out[i].dest_pe)
                        dest_q[dest_pe//num_pe_per_fpga][i].append((dest_pe, msg))
                        sender = (yield self.cores[core].network.external_network_interface_out[i].msg.sender)
                        logger.debug("IN: Message from PE {} (FPGA {}) to PE {} (FPGA {})".format(sender, sender//num_pe_per_fpga, dest_pe, dest_pe//num_pe_per_fpga))



    def gen_input(self):
        logger = logging.getLogger('simulation.input')
        num_pe = self.config.addresslayout.num_pe
        num_nodes_per_pe = self.config.addresslayout.num_nodes_per_pe

        init_messages = self.config.init_messages

        start_message = [a.start_message for core in self.cores for a in core.network.arbiter]

        for i in range(num_pe):
            yield start_message[i].select.eq(1)
            yield start_message[i].valid.eq(0)
            yield start_message[i].msg.halt.eq(0)

        while [x for l in init_messages for x in l]:
            for i in range(num_pe):
                if (yield start_message[i].ack):
                    if init_messages[i]:
                        message = init_messages[i].pop()
                        yield start_message[i].msg.dest_id.eq(message['dest_id'])
                        yield start_message[i].msg.sender.eq(message['sender'])
                        yield start_message[i].msg.payload.eq(message['payload'])
                        yield start_message[i].msg.roundpar.eq(self.config.addresslayout.num_channels - 1)
                        yield start_message[i].msg.barrier.eq(0)
                        yield start_message[i].valid.eq(1)
                    else:
                        yield start_message[i].valid.eq(0)
            yield

        for i in range(num_pe):
            yield start_message[i].msg.dest_id.eq(0)
            yield start_message[i].msg.payload.eq(0)
            yield start_message[i].msg.sender.eq(i<<log2_int(num_nodes_per_pe))
            yield start_message[i].msg.roundpar.eq(self.config.addresslayout.num_channels - 1)
            yield start_message[i].msg.barrier.eq(1)
            yield start_message[i].valid.eq(1)

        barrier_done = [0 for i in range(num_pe)]

        while 0 in barrier_done:
            yield
            for i in range(num_pe):
                if (yield start_message[i].ack):
                    yield start_message[i].valid.eq(0)
                    barrier_done[i] = 1

        for i in range(num_pe):
            yield start_message[i].select.eq(0)

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

def get_simulators(module, name, *args, **kwargs):
    simulators = []
    if hasattr(module, name):
        simulators.append(getattr(module, name)(*args, **kwargs))
    for _, submodule in module._submodules:
            for simulator in get_simulators(submodule, name, *args, **kwargs):
                    simulators.append(simulator)
    return simulators

def sim(config):

    tb = SimTop(config)

    generators = []

    for core in tb.cores:
        generators.extend([core.gen_barrier_monitor(tb)])
        generators.extend(get_simulators(core, 'gen_selfcheck', tb))
        generators.extend(get_simulators(core, 'gen_simulation', tb))

    generators.extend([tb.gen_input()])
    generators.extend([tb.gen_inter_fpga_connections()])
    # generators.extend([a.gen_stats(tb) for a in tb.apply])
    # generators.extend([tb.gen_network_stats()])

    run_simulation(tb, generators, vcd_name="tb.vcd")

def export(config, filename='top_multi.v'):

    m = SimTop(config)

    so = dict(migen.build.xilinx.common.xilinx_special_overrides)
    verilog.convert(m,
                    name="top",
                    ios=set(),
                    special_overrides=so,
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
