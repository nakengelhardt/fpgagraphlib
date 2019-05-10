from migen import *
from migen.genlib.roundrobin import *

from functools import reduce
from operator import and_
import logging

from recordfifo import *
from core_interfaces import *
from inverted_barriercounter import Barriercounter

class SimpleRoundrobin(Module):
    def __init__(self, config, in_array):
        self.apply_interface_out = ApplyInterface(name="mux_apply_interface_out", **config.addresslayout.get_params())
        self.current_round = Signal(config.addresslayout.channel_bits)

        if len(in_array) == 1:
            self.comb += in_array[0].connect(self.apply_interface_out)
        else:
            self.submodules.roundrobin = RoundRobin(len(in_array), switch_policy=SP_CE)
            # arrays for choosing incoming fifo to use
            array_msg = Array(interface.msg.raw_bits() for interface in in_array)
            array_ack = Array(interface.ack for interface in in_array)
            array_valid = Array(interface.valid for interface in in_array)
            array_round = Array(interface.msg.roundpar for interface in in_array)

            self.comb += [
                self.apply_interface_out.msg.raw_bits().eq(array_msg[self.roundrobin.grant]),
                self.apply_interface_out.valid.eq(array_valid[self.roundrobin.grant] & (array_round[self.roundrobin.grant] == self.current_round)),
                array_ack[self.roundrobin.grant].eq(self.apply_interface_out.ack & (array_round[self.roundrobin.grant] == self.current_round)),
                [self.roundrobin.request[i].eq(array_valid[i] & (array_round[i] == self.current_round)) for i in range(len(in_array))],
                self.roundrobin.ce.eq(1)
            ]

class Broadcaster(Module):
    def __init__(self, config, out_array):
        self.apply_interface_in = ApplyInterface(name="mux_apply_interface_in", **config.addresslayout.get_params())
        if len(out_array) == 1:
            self.comb += self.apply_interface_in.connect(out_array[0])
        else:
            transaction_ok = Signal()
            self.comb += [
                transaction_ok.eq(reduce(and_, [out.ack for out in out_array])),
                [self.apply_interface_in.connect(out, omit={'valid', 'ack'}) for out in out_array],
                [out.valid.eq(self.apply_interface_in.valid & transaction_ok) for out in out_array],
                self.apply_interface_in.ack.eq(transaction_ok)
            ]

class RecipientFilter(Module):
    def __init__(self, config, fpga_id, dest_fpga):
        self.fpga_id = fpga_id
        self.apply_interface_in = ApplyInterface(name="filter_in", **config.addresslayout.get_params())
        self.apply_interface_out = ApplyInterface(name="filter_out", **config.addresslayout.get_params())

        self.submodules.fifo = InterfaceFIFO(layout=self.apply_interface_in.layout, depth=8)

        self.comb += [
            self.apply_interface_in.connect(self.fifo.din)
        ]

        max_node = config.addresslayout.max_node(config.adj_dict)
        neighbor_filter = [1 for _ in range(max_node + 1)]
        for node in config.adj_dict:
            for neighbor in config.adj_dict[node]:
                if config.addresslayout.fpga_adr(neighbor) == dest_fpga:
                    neighbor_filter[node] = 0

        self.specials.filter_store = Memory(width=1, depth=max_node + 1, init=neighbor_filter)
        self.specials.rd_port = self.filter_store.get_port(async_read=True)

        self.filter = Signal()
        self.comb += [
            self.rd_port.adr.eq(self.fifo.dout.msg.sender),
            self.filter.eq(self.rd_port.dat_r & self.fifo.dout.valid & ~self.fifo.dout.msg.barrier),
        ]

        self.num_messages_filtered = Array(Signal(32) for _ in range(config.addresslayout.num_pe_per_fpga))
        self.filter_origin_pe = local_pe_adr = Signal(config.addresslayout.peidsize)
        self.comb += [
            local_pe_adr.eq(config.addresslayout.pe_adr(self.fifo.dout.msg.sender) - fpga_id*config.addresslayout.num_pe_per_fpga),
            self.fifo.dout.msg.connect(self.apply_interface_out.msg, omit={'dest_id'}),
            self.apply_interface_out.msg.dest_id.eq(self.fifo.dout.msg.dest_id - self.num_messages_filtered[local_pe_adr]),
            self.apply_interface_out.valid.eq(self.fifo.dout.valid & ~self.filter),
            self.fifo.dout.ack.eq(self.apply_interface_out.ack | self.filter)
        ]


        self.sync += [
            If(self.fifo.dout.valid & self.fifo.dout.ack,
                If(self.fifo.dout.msg.barrier,
                    self.num_messages_filtered[local_pe_adr].eq(0)
                ).Elif(self.filter,
                    self.num_messages_filtered[local_pe_adr].eq(self.num_messages_filtered[local_pe_adr] + 1)
                )
            )
        ]

    @passive
    def gen_selfcheck(self, tb):
        logger = logging.getLogger("sim.filter")
        while True:
            if (yield self.filter) and (yield self.fifo.dout.ack):
                logger.debug("Filtering update from node {} which has no neighbors on FPGA {}. (self.num_messages_filtered[{}] += 1)".format((yield self.fifo.dout.msg.sender), self.fpga_id, (yield self.filter_origin_pe)))
            yield

class UpdateNetwork(Module):
    def __init__(self, config, fpga_id):
        num_pe = config.addresslayout.num_pe_per_fpga
        num_fpga = config.addresslayout.num_fpga
        self.apply_interface_in = [ApplyInterface(name="network_in", **config.addresslayout.get_params()) for _ in range(num_pe)]
        self.scatter_interface_out = [ScatterInterface(name="network_out", **config.addresslayout.get_params()) for _ in range(num_pe)]

        self.external_network_interface_in = [ApplyInterface(name="ext_network_in", **config.addresslayout.get_params()) for _ in range(num_fpga - 1)]
        self.external_network_interface_out = [ApplyInterface(name="ext_network_out", **config.addresslayout.get_params()) for _ in range(num_fpga - 1)]

        self.submodules.srr = SimpleRoundrobin(config, self.apply_interface_in)
        self.submodules.ext_srr = SimpleRoundrobin(config, self.external_network_interface_in)

        self.submodules.fifos = [InterfaceFIFO(layout=self.apply_interface_in[0].layout, depth=8, name="link_{}".format(sink)) for sink in range(num_pe)]

        self.submodules.ext_fifos = [InterfaceFIFO(layout=self.apply_interface_in[0].layout, depth=8, name="ext_link_{}".format(sink)) for sink in range(num_fpga - 1)]

        self.submodules.broadcaster = Broadcaster(config, [fifo.din for fifo in self.fifos])
        self.submodules.ext_broadcaster = Broadcaster(config, [fifo.din for fifo in self.ext_fifos])

        # Two inputs and two outputs (internal and external)
        # inputs from internal PEs are sent to both internal and external
        # inputs from external PEs are only sent to internal (otherwise broadcast loop occurs)
        transaction_ok = Signal()
        self.comb += [
            transaction_ok.eq(self.broadcaster.apply_interface_in.ack & self.ext_broadcaster.apply_interface_in.ack),
            # prioritize receiving over sending on FPGA level
            If(self.ext_srr.apply_interface_out.valid,
                self.ext_srr.apply_interface_out.connect(self.broadcaster.apply_interface_in)
            ).Else(
                self.srr.apply_interface_out.connect(self.broadcaster.apply_interface_in, omit={'valid', 'ack'}),
                self.srr.apply_interface_out.connect(self.ext_broadcaster.apply_interface_in, omit={'valid', 'ack'}),
                self.broadcaster.apply_interface_in.valid.eq(self.srr.apply_interface_out.valid & transaction_ok),
                self.ext_broadcaster.apply_interface_in.valid.eq(self.srr.apply_interface_out.valid & transaction_ok),
                self.srr.apply_interface_out.ack.eq(transaction_ok)
            )
        ]

        # connect end of fifo to barriercounter and barriercounter to local output
        # detect local end of computation at each barriercounter and don't propagate barrier message
        self.submodules.bc = [Barriercounter(config) for _ in range(num_pe)]
        computation_end = [Signal() for _ in range(num_pe)]

        for i in range(num_pe):
            halt = Signal()
            self.comb += [
                self.fifos[i].dout.connect(self.bc[i].apply_interface_in),
                self.scatter_interface_out[i].barrier.eq(self.bc[i].apply_interface_out.msg.barrier),
                self.scatter_interface_out[i].roundpar.eq(self.bc[i].apply_interface_out.msg.roundpar),
                self.scatter_interface_out[i].sender.eq(self.bc[i].apply_interface_out.msg.sender),
                self.scatter_interface_out[i].payload.eq(self.bc[i].apply_interface_out.msg.payload),
                halt.eq(self.bc[i].apply_interface_out.valid & self.bc[i].apply_interface_out.msg.barrier & self.bc[i].apply_interface_out.msg.halt),
                self.scatter_interface_out[i].valid.eq(self.bc[i].apply_interface_out.valid & ~halt),
                self.bc[i].apply_interface_out.ack.eq(self.scatter_interface_out[i].ack | halt)
            ]

            self.sync += If(halt,
                computation_end[i].eq(1)
            )

        if config.filter:
            # filter fpgas that don't have neighbors
            other_fpgas = [x for x in range(num_fpga)]
            other_fpgas.remove(fpga_id)
            for i in range(num_fpga - 1):
                filter = RecipientFilter(config, fpga_id, other_fpgas[i])
                self.submodules += filter
                self.comb += [
                    self.ext_fifos[i].dout.connect(filter.apply_interface_in),
                    filter.apply_interface_out.connect(self.external_network_interface_out[i])
                ]
        else:
            self.comb += [self.ext_fifos[i].dout.connect(self.external_network_interface_out[i]) for i in range(num_fpga - 1)]


        # do switchover to next round
        network_round = Signal(config.addresslayout.channel_bits)
        next_round = Signal(config.addresslayout.channel_bits)
        proceed = Signal()

        self.comb += [
            proceed.eq(reduce(and_, [bc.round_accepting == next_round for bc in self.bc])),
            If(network_round < config.addresslayout.num_channels - 1,
                next_round.eq(network_round + 1)
            ).Else(
                next_round.eq(0)
            )
        ]

        self.sync += If(proceed,
            network_round.eq(next_round)
        )

        self.comb += [
            self.srr.current_round.eq(network_round),
            self.ext_srr.current_round.eq(network_round)
        ]

        # detect end of computation
        self.inactive = Signal()
        self.comb += self.inactive.eq(reduce(and_, computation_end))

        self.num_messages_to = [Signal(32) for _ in range(num_fpga - 1)]
        self.sync += [ If(self.external_network_interface_out[i].valid & self.external_network_interface_out[i].ack,
            self.num_messages_to[i].eq(self.num_messages_to[i] + 1)
        ) for i in range(num_fpga - 1)]

        self.num_messages_from = [Signal(32) for _ in range(num_fpga - 1)]
        self.sync += [ If(self.external_network_interface_in[i].valid & self.external_network_interface_in[i].ack,
            self.num_messages_from[i].eq(self.num_messages_from[i] + 1)
        ) for i in range(num_fpga - 1)]
