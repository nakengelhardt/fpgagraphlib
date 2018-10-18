from migen import *
from migen.genlib.fsm import *
from migen.genlib.fifo import *

import logging

from recordfifo import *
from core_interfaces import _neighbor_in_layout, _neighbor_out_layout

_data_layout = [
    ("message", "updatepayloadsize"),
    ("sender", "nodeidsize"),
    ("round", "channel_bits"),
    ("num_neighbors", "edgeidsize"),
    ("valid", "log_edges_per_burst")
]

class NeighborsDDR(Module):
    def __init__(self, pe_id, config, edge_data=None, port=None):
        self.pe_id = pe_id
        self.port = port
        nodeidsize = config.addresslayout.nodeidsize
        edgeidsize = config.addresslayout.edgeidsize

        # input
        self.neighbor_in = Record(set_layout_parameters(_neighbor_in_layout, **config.addresslayout.get_params()))

        # output
        self.neighbor_out = Record(set_layout_parameters(_neighbor_out_layout, **config.addresslayout.get_params()))

        ###

        assert(nodeidsize <= 32)

        # TODO: acquire port
        # if not port:
        #     port = ???

        max_inflight = 128
        num_inflight = Signal(max=max_inflight)

        edges_per_burst = len(port.rdata)//32
        burst_bytes = len(port.rdata)//8

        update_dat_w = Record(set_layout_parameters(_data_layout, log_edges_per_burst=log2_int(edges_per_burst), **config.addresslayout.get_params()))

        self.submodules.answerbuffer = SyncFIFOBuffered(width=len(port.rdata), depth=max_inflight)
        self.submodules.updatebuffer = SyncFIFOBuffered(width=layout_len(update_dat_w.layout), depth=max_inflight)

        self.comb += [
            self.updatebuffer.din.eq(update_dat_w.raw_bits())
        ]

        neighbor_in_p = Record(set_layout_parameters(_neighbor_in_layout, **config.addresslayout.get_params()))
        end_node_idx_p = Signal(edgeidsize)

        self.sync += [
            If(self.neighbor_in.ack,
                self.neighbor_in.connect(neighbor_in_p, omit=["ack"]),
                end_node_idx_p.eq(self.neighbor_in.start_idx + (self.neighbor_in.num_neighbors << 2))
            )
        ]

        self.comb += [
            self.neighbor_in.ack.eq(neighbor_in_p.ack)
        ]

        current_node_idx = Signal(edgeidsize)
        end_node_idx = Signal(edgeidsize)
        last_neighbor = Signal()

        message = Signal(config.addresslayout.updatepayloadsize)
        sender = Signal(config.addresslayout.nodeidsize)
        roundpar = Signal(config.addresslayout.channel_bits)
        num_neighbors = Signal(edgeidsize)

        self.submodules.neighbor_out_fifo = InterfaceFIFO(layout=self.neighbor_out.layout, depth=8)

        self.submodules.fsm = fsm = FSM()
        fsm.act("IDLE", # wait for input
            neighbor_in_p.ack.eq(1),
            NextValue(message, neighbor_in_p.message),
            NextValue(sender, neighbor_in_p.sender),
            NextValue(roundpar, neighbor_in_p.round),
            NextValue(num_neighbors, neighbor_in_p.num_neighbors),
            If(neighbor_in_p.barrier,
                NextState("BARRIER")
            ),
            If(neighbor_in_p.valid & (neighbor_in_p.num_neighbors != 0),
                NextValue(current_node_idx, neighbor_in_p.start_idx),
                NextValue(end_node_idx, end_node_idx_p),
                NextState("GET_NEIGHBORS")
            )
        )

        fsm.act("GET_NEIGHBORS",
            port.arvalid.eq(num_inflight < (max_inflight - 1)),
            If(port.arvalid & port.arready,
                NextValue(current_node_idx, current_node_idx + burst_bytes),
                If(current_node_idx + burst_bytes >= end_node_idx,
                    NextState("IDLE")
                )
            )
        )
        self.comb += [
            port.araddr.eq(current_node_idx),
            self.updatebuffer.we.eq(port.arready & port.arvalid),
            update_dat_w.message.eq(message),
            update_dat_w.sender.eq(sender),
            update_dat_w.round.eq(roundpar),
            update_dat_w.num_neighbors.eq(num_neighbors),
            If(current_node_idx + burst_bytes <= end_node_idx,
                update_dat_w.valid.eq(edges_per_burst-1)
            ).Else(
                update_dat_w.valid.eq(num_neighbors[:log2_int(edges_per_burst)]-1)
            )
        ]

        fsm.act("BARRIER",
            If((num_inflight == 0) & ~self.neighbor_out_fifo.din.valid,
                NextValue(self.neighbor_out_fifo.din.barrier, 1),
                NextState("BARRIER_WAIT")
            )
        )
        fsm.act("BARRIER_WAIT",
            If(self.neighbor_out_fifo.din.ack,
                NextValue(self.neighbor_out_fifo.din.barrier, 0),
                NextState("IDLE")
            )
        )

        # count inflight requests
        plus_one = Signal()
        minus_one = Signal()
        self.comb += [
            If(port.arready & port.arvalid,
                plus_one.eq(1)
            ).Else(
                plus_one.eq(0)
            ),
            If(self.answerbuffer.readable & self.answerbuffer.re,
                minus_one.eq(1)
            ).Else(
                minus_one.eq(0)
            )
        ]

        self.sync += [
            num_inflight.eq(num_inflight + plus_one - minus_one)
        ]

        # receive bursts from DDR
        self.comb += [
            self.answerbuffer.din.eq(port.rdata),
            self.answerbuffer.we.eq(port.rvalid),
            port.rready.eq(self.answerbuffer.writable)
        ]

        # look up available answer data in memories
        update_dat_r = Record(set_layout_parameters(_data_layout, log_edges_per_burst=log2_int(edges_per_burst), **config.addresslayout.get_params()))
        burst_valid = Signal()
        burst_done = Signal()
        self.comb += [
            burst_valid.eq(self.answerbuffer.readable & self.updatebuffer.readable),
            self.answerbuffer.re.eq(burst_valid & burst_done),
            self.updatebuffer.re.eq(burst_valid & burst_done),
            update_dat_r.raw_bits().eq(self.updatebuffer.dout)
        ]


        # downconvert bursts
        mux = Signal(max=edges_per_burst + 1)
        last = Signal()
        self.comb += [
            last.eq(mux == update_dat_r.valid),
            burst_done.eq(last & self.neighbor_out_fifo.din.ack)
        ]

        self.sync += [
            If(self.neighbor_out_fifo.din.valid & self.neighbor_out_fifo.din.ack & ~self.neighbor_out_fifo.din.barrier,
                If(last,
                    mux.eq(0)
                ).Else(
                    mux.eq(mux + 1)
                )
            )
        ]

        cases = {}
        for i in range(edges_per_burst):
            cases[i] = self.neighbor_out_fifo.din.neighbor.eq(self.answerbuffer.dout[i*32:(i+1)*32])
        self.comb += Case(mux, cases).makedefault()

        # output
        self.comb += [
            If(self.neighbor_out_fifo.din.barrier,
                self.neighbor_out_fifo.din.valid.eq(1),
                self.neighbor_out_fifo.din.message.eq(message),
                self.neighbor_out_fifo.din.sender.eq(sender),
                self.neighbor_out_fifo.din.round.eq(roundpar),
                self.neighbor_out_fifo.din.num_neighbors.eq(num_neighbors)
            ).Else(
                self.neighbor_out_fifo.din.valid.eq(burst_valid),
                self.neighbor_out_fifo.din.message.eq(update_dat_r.message),
                self.neighbor_out_fifo.din.sender.eq(update_dat_r.sender),
                self.neighbor_out_fifo.din.round.eq(update_dat_r.round),
                self.neighbor_out_fifo.din.num_neighbors.eq(update_dat_r.num_neighbors)
            ),
            self.neighbor_out_fifo.dout.connect(self.neighbor_out, omit={"valid", "barrier"}),
            self.neighbor_out.barrier.eq(self.neighbor_out_fifo.dout.valid & self.neighbor_out_fifo.dout.barrier),
            self.neighbor_out.valid.eq(self.neighbor_out_fifo.dout.valid & ~self.neighbor_out_fifo.dout.barrier)
        ]

        self.requests_emitted = Signal(32)
        self.requests_fulfilled = Signal(32)

        self.sync += [
            If(port.arready & port.arvalid,
                self.requests_emitted.eq(self.requests_emitted + 1)
            ),
            If(port.rready & port.rvalid,
                self.requests_fulfilled.eq(self.requests_fulfilled + 1)
            )
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
            if (yield self.port.arvalid) and (yield self.port.arready):
                num_mem_reads += 1
            if (yield self.neighbor_out.valid) and (yield self.neighbor_out.ack):
                neighbor = (yield self.neighbor_out.neighbor)
                curr_sender = (yield self.neighbor_out.sender)
                logger.debug("{}: Message from node {} for node {}".format(num_cycles, curr_sender, neighbor))
                if tb.config.has_edgedata:
                    logger.debug("Edgedata: " + str((yield self.edgedata_out)))
                if (not curr_sender in to_be_sent) or (not neighbor in to_be_sent[curr_sender]):
                    if not neighbor in graph[curr_sender]:
                        logger.warning("{}: sending message to node {} which is not a neighbor of {}! (Neighbors: {})".format(num_cycles, neighbor, curr_sender, graph[curr_sender]))
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
