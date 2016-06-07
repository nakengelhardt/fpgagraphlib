from migen import *
from migen.genlib.fsm import FSM, NextState, NextValue

import logging

class Neighbors(Module):
    def __init__(self, config, adj_val, edge_data=None):
        nodeidsize = config.addresslayout.nodeidsize
        num_nodes_per_pe = config.addresslayout.num_nodes_per_pe
        edgeidsize = config.addresslayout.edgeidsize
        max_edges_per_pe = config.addresslayout.max_edges_per_pe

        # input
        self.start_idx = Signal(edgeidsize)
        self.num_neighbors = Signal(edgeidsize)
        self.valid = Signal()
        self.ack = Signal()
        self.barrier_in = Signal()
        self.message_in = Signal(config.addresslayout.payloadsize)
        self.sender_in = Signal(config.addresslayout.nodeidsize)
        self.round_in = Signal()

        # output
        self.neighbor = Signal(nodeidsize)
        self.neighbor_valid = Signal()
        self.neighbor_ack = Signal()
        self.barrier_out = Signal()
        self.message_out = Signal(config.addresslayout.payloadsize)
        self.sender_out = Signal(config.addresslayout.nodeidsize)
        self.round_out = Signal()
        self.num_neighbors_out = Signal(edgeidsize)
        if config.has_edgedata:
            self.edgedata_out = Signal(config.addresslayout.edgedatasize)
        ###

        # adjacency list storage (second half of CSR storage, index comes from input)
        # val: array of nodeids
        self.specials.mem_val = Memory(nodeidsize, max_edges_per_pe, init=adj_val)
        self.specials.rd_port_val = rd_port_val = self.mem_val.get_port(has_re=True)
        # self.specials.wr_port_val = wr_port_val = self.mem_val.get_port(write_capable=True)

        if config.has_edgedata:
            self.specials.mem_edge = Memory(config.addresslayout.edgedatasize, max_edges_per_pe, init=edge_data)
            self.specials.rd_port_edge = rd_port_edge = self.mem_edge.get_port(has_re=True)

        next_node_idx = Signal(edgeidsize)
        end_node_idx = Signal(edgeidsize)
        idx_valid = Signal()
        last_neighbor = Signal()

        # control path
        self.submodules.fsm = fsm = FSM()
        fsm.act("IDLE", # wait for input
            self.ack.eq(1),
            rd_port_val.adr.eq(self.start_idx),
            rd_port_val.re.eq(1),
            rd_port_edge.adr.eq(self.start_idx) if config.has_edgedata else [],
            rd_port_edge.re.eq(1) if config.has_edgedata else [],
            NextValue(self.message_out, self.message_in),
            NextValue(self.sender_out, self.sender_in),
            NextValue(self.round_out, self.round_in),
            NextValue(self.num_neighbors_out, self.num_neighbors),
            If(self.barrier_in,
                NextState("BARRIER")
            ),
            If(self.valid & (self.num_neighbors != 0),
                NextValue(next_node_idx, self.start_idx + 1),
                NextValue(end_node_idx, self.start_idx + self.num_neighbors),
                NextState("GET_NEIGHBORS")
            )
        )
        fsm.act("GET_NEIGHBORS", # iterate over neighbors
            self.neighbor_valid.eq(1),
            rd_port_val.adr.eq(next_node_idx),
            rd_port_edge.adr.eq(next_node_idx) if config.has_edgedata else [],
            If(self.neighbor_ack,
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
            self.barrier_out.eq(1),
            If(self.neighbor_ack,
                NextState("IDLE")
            )
        )

        # data path
        self.comb += [
            self.neighbor.eq(rd_port_val.dat_r),
            self.edgedata_out.eq(rd_port_edge.dat_r) if config.has_edgedata else []
        ]

        # stats
        self.num_requests_accepted = Signal(32)
        self.num_neighbors_issued = Signal(32)

        self.sync += [
            If(self.valid & self.ack, self.num_requests_accepted.eq(self.num_requests_accepted + 1)),
            If(self.neighbor_valid & self.neighbor_ack, self.num_neighbors_issued.eq(self.num_neighbors_issued + 1))
        ]


    def gen_selfcheck(self, tb, graph):
        logger = logging.getLogger('simulation.get_neighbors')
        curr_sender = 0
        to_be_sent = []
        level = 0
        num_cycles = 0
        num_mem_reads = 0
        while not (yield tb.global_inactive):
            num_cycles += 1
            if (yield self.barrier_out):
                level += 1
            if (yield self.neighbor_valid) and (yield self.neighbor_ack):
                num_mem_reads += 1
                neighbor = (yield self.neighbor)
                logger.debug("{}: Message from node {} for node {}".format(num_cycles, curr_sender, neighbor))
                if tb.config.has_edgedata:
                    logger.debug("Edgedata: " + str((yield self.edgedata_out)))
                if not neighbor in to_be_sent:
                    if not neighbor in graph[curr_sender]:
                        logger.warning("{}: sending message to node {} which is not a neighbor of {}!".format(num_cycles, neighbor, curr_sender))
                    else:
                        logger.warning("{}: sending message to node {} more than once from node {}".format(num_cycles, neighbor, curr_sender))
                else:
                    to_be_sent.remove(neighbor)
            if (yield self.valid) and (yield self.ack):
                if to_be_sent:
                    logger.warning("{}: message for nodes {} was not sent from node {}".format(num_cycles, to_be_sent, curr_sender))
                curr_sender = (yield self.sender_in)
                if not curr_sender in graph:
                    logger.warning("{}: invalid sender ({})".format(num_cycles, curr_sender))
                    to_be_sent = []
                else:
                    to_be_sent = list(graph[curr_sender])
            yield
        logger.info("{} memory reads.".format(num_mem_reads))
