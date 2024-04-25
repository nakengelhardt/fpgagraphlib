from migen import *
from migen.genlib.fsm import FSM, NextState, NextValue

from util.mem import FullyInitMemory

import logging

from core_interfaces import _neighbor_in_layout, _neighbor_out_layout

class Neighbors(Module):
    def __init__(self, pe_id, config, port=None):
        self.pe_id = pe_id
        nodeidsize = config.addresslayout.nodeidsize
        num_nodes_per_pe = config.addresslayout.num_nodes_per_pe
        edgeidsize = config.addresslayout.edgeidsize
        max_edges_per_pe = config.addresslayout.max_edges_per_pe

        # input
        self.neighbor_in = Record(set_layout_parameters(_neighbor_in_layout, **config.addresslayout.get_params()))

        # output
        self.neighbor_out = Record(set_layout_parameters(_neighbor_out_layout, **config.addresslayout.get_params()))
        if config.has_edgedata:
            self.edgedata_out = Signal(config.addresslayout.edgedatasize)
        ###

        # adjacency list storage (second half of CSR storage, index comes from input)
        # val: array of nodeids
        self.specials.mem_val = FullyInitMemory(nodeidsize, len(config.adj_val[pe_id]) + 2, name="edge_csr_val", init=config.adj_val[pe_id])
        # self.specials.mem_val = FullyInitMemory(nodeidsize, max_edges_per_pe, init=adj_val)
        self.specials.rd_port_val = rd_port_val = self.mem_val.get_port(has_re=True)
        self.specials.wr_port_val = self.mem_val.get_port(write_capable=True)

        if config.has_edgedata:
            self.specials.mem_edge = FullyInitMemory(config.addresslayout.edgedatasize, len(config.adj_val[pe_id]) + 2, init=config.init_edgedata[pe_id])
            self.specials.rd_port_edge = rd_port_edge = self.mem_edge.get_port(has_re=True)
            self.specials.wr_port_edge = self.mem_edge.get_port(write_capable=True)

        next_node_idx = Signal(edgeidsize)
        end_node_idx = Signal(edgeidsize)
        idx_valid = Signal()
        last_neighbor = Signal()

        # control path
        self.submodules.fsm = fsm = FSM()
        fsm.act("IDLE", # wait for input
            self.neighbor_in.ack.eq(1),
            rd_port_val.adr.eq(self.neighbor_in.start_idx),
            rd_port_val.re.eq(1),
            rd_port_edge.adr.eq(self.neighbor_in.start_idx) if config.has_edgedata else [],
            rd_port_edge.re.eq(1) if config.has_edgedata else [],
            NextValue(self.neighbor_out.message, self.neighbor_in.message),
            NextValue(self.neighbor_out.sender, self.neighbor_in.sender),
            NextValue(self.neighbor_out.round, self.neighbor_in.round),
            NextValue(self.neighbor_out.num_neighbors, self.neighbor_in.num_neighbors),
            If(self.neighbor_in.barrier,
                NextState("BARRIER")
            ),
            If(self.neighbor_in.valid & (self.neighbor_in.num_neighbors != 0),
                NextValue(next_node_idx, self.neighbor_in.start_idx + 1),
                NextValue(end_node_idx, self.neighbor_in.start_idx + self.neighbor_in.num_neighbors),
                NextState("GET_NEIGHBORS")
            )
        )
        fsm.act("GET_NEIGHBORS", # iterate over neighbors
            self.neighbor_out.valid.eq(1),
            rd_port_val.adr.eq(next_node_idx),
            rd_port_edge.adr.eq(next_node_idx) if config.has_edgedata else [],
            If(self.neighbor_out.ack,
                rd_port_val.re.eq(1),
                rd_port_edge.re.eq(1) if config.has_edgedata else [],
                If(next_node_idx == end_node_idx,
                    NextState("IDLE")
                ).Else(
                    NextValue(next_node_idx, next_node_idx + 1)
                )
            )
        )
        fsm.act("BARRIER",
            self.neighbor_out.barrier.eq(1),
            If(self.neighbor_out.ack,
                NextState("IDLE")
            )
        )

        # data path
        self.comb += [
            self.neighbor_out.neighbor.eq(rd_port_val.dat_r),
            self.edgedata_out.eq(rd_port_edge.dat_r) if config.has_edgedata else []
        ]

        # stats
        self.num_updates_accepted = Signal(32)
        self.num_neighbors_requested = Signal(32)
        self.num_neighbors_issued = Signal(32)

        self.sync += [
            If(self.neighbor_in.valid & self.neighbor_in.ack,
                self.num_updates_accepted.eq(self.num_updates_accepted + 1),
                self.num_neighbors_requested.eq(self.num_neighbors_requested + self.neighbor_in.num_neighbors)
            ),
            If(self.neighbor_out.valid & self.neighbor_out.ack,
                self.num_neighbors_issued.eq(self.num_neighbors_issued + 1)
            )
        ]


    def gen_selfcheck(self, tb):
        logger = logging.getLogger('sim.get_neighbors' + str(self.pe_id))
        graph = tb.config.adj_dict
        curr_sender = 0
        to_be_sent = []
        level = 0
        num_cycles = 0
        num_mem_reads = 0
        while not (yield tb.global_inactive):
            num_cycles += 1
            if (yield self.neighbor_out.barrier):
                level += 1
            if (yield self.neighbor_out.valid) and (yield self.neighbor_out.ack):
                num_mem_reads += 1
                neighbor = (yield self.neighbor_out.neighbor)
                logger.debug("{}: Edge {} -> {} read.{}".format(num_cycles, curr_sender, neighbor, " Edgedata: " + str((yield self.edgedata_out)) if tb.config.has_edgedata else ""))
                if not neighbor in to_be_sent:
                    if not neighbor in graph[curr_sender]:
                        logger.warning("{}: sending message to node {} which is not a neighbor of {}!".format(num_cycles, neighbor, curr_sender))
                    elif tb.config.inverted and tb.config.addresslayout.pe_adr(neighbor) != self.pe_id:
                        logger.warning("{}: sending message to node {} which is not located on this PE (from node {})".format(num_cycles, neighbor, curr_sender))
                    else:
                        logger.warning("{}: sending message to node {} more than once from node {}".format(num_cycles, neighbor, curr_sender))
                else:
                    to_be_sent.remove(neighbor)
            if (yield self.neighbor_in.valid) and (yield self.neighbor_in.ack):
                if to_be_sent:
                    logger.warning("{}: message for nodes {} was not sent from node {}".format(num_cycles, to_be_sent, curr_sender))
                curr_sender = (yield self.neighbor_in.sender)
                if not curr_sender in graph:
                    logger.warning("{}: invalid sender ({})".format(num_cycles, curr_sender))
                    to_be_sent = []
                else:
                    if tb.config.inverted:
                        to_be_sent = [n for n in graph[curr_sender] if tb.config.addresslayout.pe_adr(n) == self.pe_id]
                    else:
                        to_be_sent = list(graph[curr_sender])
            yield
        logger.info("{} memory reads.".format(num_mem_reads))
