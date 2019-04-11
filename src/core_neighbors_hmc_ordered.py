from migen import *
from migen.genlib.fsm import FSM, NextState, NextValue

import logging
import math

from core_interfaces import _neighbor_in_layout, _neighbor_out_layout
from get_edgelist import GetEdgelistHMC
from recordfifo import RecordFIFO

class NeighborsHMC(Module):
    def __init__(self, pe_id, config, hmc_port=None):
        self.pe_id = pe_id
        nodeidsize = config.addresslayout.nodeidsize
        edgeidsize = config.addresslayout.edgeidsize
        if config.has_edgedata:
            edgedatasize = config.addresslayout.edgedatasize
        else:
            edgedatasize = 0

        if not hmc_port:
            hmc_port = config.platform.getHMCPort(pe_id % config.addresslayout.num_pe_per_fpga)

        self.hmc_port = hmc_port
        effective_max_tag_size = self.hmc_port.effective_max_tag_size

        vertex_size = max(8,2**math.ceil(math.log2(nodeidsize + edgedatasize)))
        # vertex_size = 32
        vtx_offset = log2_int(vertex_size//8)
        vertices_per_flit = len(hmc_port.rd_data)//vertex_size

        # input
        self.neighbor_in = Record(set_layout_parameters(_neighbor_in_layout, **config.addresslayout.get_params()))

        # output
        self.neighbor_out = Record(set_layout_parameters(_neighbor_out_layout, **config.addresslayout.get_params()))
        if config.has_edgedata:
            self.edgedata_out = Signal(config.addresslayout.edgedatasize)
        ###




        self.submodules.get_edgelist = GetEdgelistHMC(hmc_port, vertex_size_in_bits=vertex_size)

        _layout = [("num_neighbors", "nodeidsize", DIR_M_TO_S),
            ("sender", "nodeidsize", DIR_M_TO_S),
            ("message", "updatepayloadsize", DIR_M_TO_S),
            ("round", "channel_bits", DIR_M_TO_S),
            ("barrier", 1, DIR_M_TO_S)]
        self.submodules.update_fifo = RecordFIFO(layout=set_layout_parameters(_layout, **config.addresslayout.get_params()), depth=64)

        self.comb += [
            self.get_edgelist.req.start_address.eq(self.neighbor_in.start_idx),
            self.get_edgelist.req.end_address.eq(self.neighbor_in.start_idx + (self.neighbor_in.num_neighbors << vtx_offset)),
            self.update_fifo.din.num_neighbors.eq(self.neighbor_in.num_neighbors),
            self.update_fifo.din.sender.eq(self.neighbor_in.sender),
            self.update_fifo.din.message.eq(self.neighbor_in.message),
            self.update_fifo.din.round.eq(self.neighbor_in.round),
            self.update_fifo.din.barrier.eq(self.neighbor_in.barrier),
            self.update_fifo.we.eq((self.neighbor_in.valid & self.get_edgelist.req.ack) | self.neighbor_in.barrier),
            self.get_edgelist.req.valid.eq(self.neighbor_in.valid & self.update_fifo.writable),
            self.neighbor_in.ack.eq((self.get_edgelist.req.ack | self.neighbor_in.barrier) & self.update_fifo.writable)
        ]

        mux = Signal(3)
        last = Signal()
        self.comb += [
            last.eq(mux == self.get_edgelist.rep.nvtx - 1),
        ]
        self.sync += [
            If(self.neighbor_out.valid & self.neighbor_out.ack,
                If(last,
                    mux.eq(0)
                ).Else(
                    mux.eq(mux + 1)
                )
            )
        ]

        cases = {}
        for i in range(vertices_per_flit):
            cases[i] = [self.neighbor_out.neighbor.eq(self.get_edgelist.rep.vertex_array[i*vertex_size:i*vertex_size + nodeidsize])]
            if config.has_edgedata:
                cases[i].append(self.edgedata_out.eq(self.get_edgelist.rep.vertex_array[i*vertex_size + nodeidsize:(i+1)*vertex_size]))
        self.comb += Case(mux, cases).makedefault()

        self.comb += [
            self.neighbor_out.num_neighbors.eq(self.update_fifo.dout.num_neighbors),
            self.neighbor_out.sender.eq(self.update_fifo.dout.sender),
            self.neighbor_out.message.eq(self.update_fifo.dout.message),
            self.neighbor_out.round.eq(self.update_fifo.dout.round),
            self.neighbor_out.barrier.eq(self.update_fifo.dout.barrier & self.update_fifo.readable),
            self.neighbor_out.valid.eq(self.update_fifo.readable & ~self.update_fifo.dout.barrier & self.get_edgelist.rep.valid),
            self.get_edgelist.rep.ack.eq((self.update_fifo.readable & ~self.update_fifo.dout.barrier & self.neighbor_out.ack & last) | ~self.get_edgelist.rep.valid),
            self.update_fifo.re.eq(self.neighbor_out.ack & ((self.get_edgelist.rep.valid & self.get_edgelist.rep.last & last) | self.update_fifo.dout.barrier))
        ]

    def gen_selfcheck(self, tb):
        logger = logging.getLogger("sim.get_neighbors" + str(self.pe_id))
        graph = tb.config.adj_dict
        to_be_sent = dict()
        level = 0
        num_cycles = 0
        num_mem_reads = 0
        while not (yield tb.global_inactive):
            num_cycles += 1
            if (yield self.neighbor_out.barrier):
                level += 1
            if (yield self.hmc_port.cmd_valid) and (yield self.hmc_port.cmd_ready):
                num_mem_reads += 1
            if (yield self.neighbor_out.valid) and (yield self.neighbor_out.ack):
                neighbor = (yield self.neighbor_out.neighbor)
                curr_sender = (yield self.neighbor_out.sender)
                logger.debug("{}: Message from node {} for node {}".format(num_cycles, curr_sender, neighbor))
                if tb.config.has_edgedata:
                    logger.debug("Edgedata: " + str((yield self.edgedata_out)))
                if (not curr_sender in to_be_sent) or (not neighbor in to_be_sent[curr_sender]):
                    if not neighbor in graph[curr_sender]:
                        logger.warning("{}: sending message to node {} which is not a neighbor of {}!".format(num_cycles, neighbor, curr_sender))
                    else:
                        logger.warning("{}: sending message to node {} more than once from node {}".format(num_cycles, neighbor, curr_sender))
                else:
                    to_be_sent[curr_sender].remove(neighbor)
            if (yield self.neighbor_in.valid) and (yield self.neighbor_in.ack):
                curr_sender = (yield self.neighbor_in.sender)
                logger.debug("request for neighbors of node {}".format(curr_sender))
                if not curr_sender in graph:
                    logger.warning("{}: invalid sender ({})".format(num_cycles, curr_sender))
                else:
                    if curr_sender in to_be_sent and to_be_sent[curr_sender]:
                        logger.warning("{}: message for nodes {} was not sent from node {}".format(num_cycles, to_be_sent[curr_sender], curr_sender))
                    to_be_sent[curr_sender] = list(graph[curr_sender])
            yield
        logger.info("{} memory reads.".format(num_mem_reads))
