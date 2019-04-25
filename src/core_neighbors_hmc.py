from migen import *
from migen.genlib.fsm import FSM, NextState, NextValue
from migen.genlib.fifo import SyncFIFO

import logging

_data_layout = [
    ("message", "updatepayloadsize"),
    ("sender", "nodeidsize"),
    ("round", "channel_bits"),
    ("num_neighbors", "edgeidsize"),
    ("valid", 2)
]

from core_interfaces import _neighbor_in_layout, _neighbor_out_layout

class getAnswer(Module):
    def __init__(self, config, update_rd_port, answer_rd_port):
        self.tag_in = Signal(6)
        self.valid_in = Signal()
        self.ack_in = Signal()

        self.tag_out = Signal(6)
        self.burst_out = Signal(128)
        self.burst_valid = Signal(2)
        self.message_out = Signal(config.addresslayout.updatepayloadsize)
        self.sender_out = Signal(config.addresslayout.nodeidsize)
        self.round_out = Signal(config.addresslayout.channel_bits)
        self.num_neighbors_out = Signal(config.addresslayout.edgeidsize)
        self.valid_out = Signal()
        self.ack_out = Signal()

        update_dat_r = Record(set_layout_parameters(_data_layout, **config.addresslayout.get_params()))
        re = Signal()

        self.comb += [
            update_dat_r.raw_bits().eq(update_rd_port.dat_r),
            re.eq(self.ack_out | ~self.valid_out),
            self.ack_in.eq(re),
            update_rd_port.adr.eq(self.tag_in),
            answer_rd_port.adr.eq(self.tag_in),
            update_rd_port.re.eq(re),
            answer_rd_port.re.eq(re),
            self.burst_out.eq(answer_rd_port.dat_r),
            self.burst_valid.eq(update_dat_r.valid),
            self.message_out.eq(update_dat_r.message),
            self.sender_out.eq(update_dat_r.sender),
            self.round_out.eq(update_dat_r.round),
            self.num_neighbors_out.eq(update_dat_r.num_neighbors),
        ]

        self.sync += [
            If(re,
                self.valid_out.eq(self.valid_in),
                self.tag_out.eq(self.tag_in)
            )
        ]




class Neighbors(Module):
    def __init__(self, pe_id, config, edge_data=None, port=None):
        self.pe_id = pe_id
        nodeidsize = config.addresslayout.nodeidsize
        edgeidsize = config.addresslayout.edgeidsize

        # input
        self.neighbor_in = Record(set_layout_parameters(_neighbor_in_layout, **config.addresslayout.get_params()))

        # output
        self.neighbor_out = Record(set_layout_parameters(_neighbor_out_layout, **config.addresslayout.get_params()))

        ###

        assert(edgeidsize <= 32)

        if not port:
            port = config.platform.getHMCPort(pe_id % config.addresslayout.num_pe_per_fpga)

        self.port = port
        effective_max_tag_size = self.port.effective_max_tag_size

        self.comb += [
            port.wr_data.eq(0),
            port.wr_data_valid.eq(0)
        ]

        num_injected = Signal(7)
        inject = Signal()

        no_tags_inflight = Signal()

        update_dat_w = Record(set_layout_parameters(_data_layout, **config.addresslayout.get_params()))

        self.submodules.tags = SyncFIFO(6, 2**effective_max_tag_size)
        self.submodules.answers = SyncFIFO(6, 2**effective_max_tag_size)
        self.specials.answerbuffer = Memory(128, 2**effective_max_tag_size)
        self.specials.answer_rd_port = self.answerbuffer.get_port(has_re=True)
        self.specials.answer_wr_port = self.answerbuffer.get_port(write_capable=True)
        self.specials.updatebuffer = Memory(len(update_dat_w), 2**effective_max_tag_size)
        self.specials.update_rd_port = self.updatebuffer.get_port(has_re=True)
        self.specials.update_wr_port = self.updatebuffer.get_port(write_capable=True)

        self.comb += [
            self.update_wr_port.dat_w.eq(update_dat_w.raw_bits())
        ]

        neighbor_in_p = Record(set_layout_parameters(_neighbor_in_layout, **config.addresslayout.get_params()))
        end_node_idx_p = Signal(edgeidsize)

        self.sync += [
            If(self.neighbor_in.ack,
                self.neighbor_in.connect(neighbor_in_p, omit={"ack"}),
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

        current_tag = Signal(6)

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
            If(neighbor_in_p.valid & (neighbor_in_p.num_neighbors > 0),
                NextValue(current_node_idx, neighbor_in_p.start_idx),
                NextValue(end_node_idx, end_node_idx_p),
                NextState("GET_NEIGHBORS")
            )
        )

        fsm.act("GET_NEIGHBORS",
            port.cmd_valid.eq(inject | self.tags.readable),
            self.tags.re.eq(port.cmd_ready & ~inject),
            If(port.cmd_valid & port.cmd_ready,
                NextValue(current_node_idx, current_node_idx + 16),
                If(current_node_idx + 16 >= end_node_idx,
                    NextState("IDLE")
                )
            )
        )
        self.comb += [
            port.addr.eq(current_node_idx),
            self.update_wr_port.adr.eq(current_tag),
            self.update_wr_port.we.eq(port.cmd_valid),
            update_dat_w.message.eq(message),
            update_dat_w.sender.eq(sender),
            update_dat_w.round.eq(roundpar),
            update_dat_w.num_neighbors.eq(num_neighbors),
            If(current_node_idx + 16 <= end_node_idx,
                update_dat_w.valid.eq(3)
            ).Else(
                update_dat_w.valid.eq(end_node_idx[2:4]-1)
            ),
            port.clk.eq(ClockSignal()),
            port.cmd.eq(0), #`define HMC_CMD_RD 4'b0000
            port.size.eq(1),
            port.tag.eq(current_tag),
        ]

        fsm.act("BARRIER",
            If(no_tags_inflight & ~self.neighbor_out.valid,
                NextValue(self.neighbor_out.barrier, 1),
                NextState("BARRIER_WAIT")
            )
        )
        fsm.act("BARRIER_WAIT",
            If(self.neighbor_out.ack,
                NextValue(self.neighbor_out.barrier, 0),
                NextState("IDLE")
            )
        )

        # tag injection
        self.sync += If(inject & port.cmd_ready & port.cmd_valid,
            num_injected.eq(num_injected + 1)
        )
        self.comb += [
            no_tags_inflight.eq(self.tags.level == num_injected),
            inject.eq(num_injected < 2**effective_max_tag_size),
            If(inject, current_tag.eq(num_injected)).Else(current_tag.eq(self.tags.dout))
        ]

        # receive bursts from HMC - save data, put tag in queue for available answers
        self.comb += [
            self.answer_wr_port.dat_w.eq(port.rd_data),
            self.answer_wr_port.adr.eq(port.rd_data_tag),
            self.answer_wr_port.we.eq(port.rd_data_valid & ~port.dinv),
            self.answers.din.eq(port.rd_data_tag),
            self.answers.we.eq(port.rd_data_valid & ~port.dinv)
        ]

        # look up available answer data in memories
        self.submodules.get_answer = getAnswer(config=config, update_rd_port=self.update_rd_port, answer_rd_port=self.answer_rd_port)

        self.comb += [
            self.get_answer.tag_in.eq(self.answers.dout),
            self.get_answer.valid_in.eq(self.answers.readable),
            self.answers.re.eq(self.get_answer.ack_in)
        ]

        # recycle tags
        self.comb += [
            self.tags.din.eq(self.get_answer.tag_out),
            self.tags.we.eq(self.get_answer.valid_out & self.get_answer.ack_out)
        ]

        # downconvert bursts
        mux = Signal(3)
        last = Signal()
        self.comb += [
            last.eq(mux == (self.get_answer.burst_valid)),
            self.get_answer.ack_out.eq(last & self.neighbor_out.ack)
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
        for i in range(4):
            cases[i] = self.neighbor_out.neighbor.eq(self.answer_rd_port.dat_r[i*32:(i+1)*32])
        self.comb += Case(mux, cases).makedefault()

        # output
        self.comb += [
            self.neighbor_out.valid.eq(self.get_answer.valid_out),
            If(self.neighbor_out.barrier,
                self.neighbor_out.message.eq(message),
                self.neighbor_out.sender.eq(sender),
                self.neighbor_out.round.eq(roundpar),
                self.neighbor_out.num_neighbors.eq(num_neighbors)
            ).Else(
                self.neighbor_out.message.eq(self.get_answer.message_out),
                self.neighbor_out.sender.eq(self.get_answer.sender_out),
                self.neighbor_out.round.eq(self.get_answer.round_out),
                self.neighbor_out.num_neighbors.eq(self.get_answer.num_neighbors_out)
            )
        ]


        # stats
        self.num_requests_accepted = Signal(32)
        self.num_hmc_commands_issued = Signal(32)
        self.num_hmc_commands_retired = Signal(32)
        self.num_hmc_responses = Signal(32)
        self.num_neighbors_issued = Signal(32)

        self.sync += [
            If(port.cmd_valid & port.cmd_ready, self.num_hmc_commands_issued.eq(self.num_hmc_commands_issued + 1)),
            If(self.answers.readable & self.answers.re, self.num_hmc_commands_retired.eq(self.num_hmc_commands_retired + 1)),
            If(port.rd_data_valid & ~port.dinv, self.num_hmc_responses.eq(self.num_hmc_responses + 1)),
            If(neighbor_in_p.valid & neighbor_in_p.ack, self.num_requests_accepted.eq(self.num_requests_accepted + 1)),
            If(self.neighbor_out.valid & self.neighbor_out.ack, self.num_neighbors_issued.eq(self.num_neighbors_issued + 1))
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
            if (yield self.port.cmd_valid) and (yield self.port.cmd_ready):
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
