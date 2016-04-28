from migen import *
from migen.genlib.fsm import FSM, NextState, NextValue
from migen.genlib.fifo import SyncFIFO

_data_layout = [
    ("message", "payloadsize"),
    ("sender", "nodeidsize"),
    ("round", 1),
    ("num_neighbors", "edgeidsize"),
    ("valid", 2)
]


class getAnswer(Module):
    def __init__(self, config, update_rd_port, answer_rd_port):
        self.tag_in = Signal(6)
        self.valid_in = Signal()
        self.ack_in = Signal()

        self.tag_out = Signal(6)
        self.burst_out = Signal(128)
        self.burst_valid = Signal(2)
        self.message_out = Signal(config.addresslayout.payloadsize)
        self.sender_out = Signal(config.addresslayout.nodeidsize)
        self.round_out = Signal()
        self.num_neighbors_out = Signal(config.addresslayout.edgeidsize)
        self.valid_out = Signal()
        self.ack_out = Signal()

        update_dat_r = Record(set_layout_parameters(_data_layout,
            nodeidsize=config.addresslayout.nodeidsize, 
            edgeidsize=config.addresslayout.edgeidsize, 
            payloadsize=config.addresslayout.payloadsize))
        re = Signal()

        self.comb += [
            update_dat_r.raw_bits().eq(update_rd_port.dat_r),
            re.eq(self.ack_out | ~self.valid_out),
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




class NeighborsHMC(Module):
    def __init__(self, config, adj_val, edge_data=None, hmc_port=None):
        nodeidsize = config.addresslayout.nodeidsize
        edgeidsize = config.addresslayout.edgeidsize

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

        ###

        assert(edgeidsize == 32)

        num_injected = Signal(7)
        inject = Signal()

        no_tags_inflight = Signal()

        if not hmc_port:
            hmc_port = config.platform.getHMCPort(0)


        update_dat_w = Record(set_layout_parameters(_data_layout,
            nodeidsize=config.addresslayout.nodeidsize, 
            edgeidsize=config.addresslayout.edgeidsize, 
            payloadsize=config.addresslayout.payloadsize))

        self.submodules.tags = SyncFIFO(6, 2**6)
        self.submodules.answers = SyncFIFO(6, 2**6)
        self.specials.answerbuffer = Memory(128, 2**6)
        self.specials.answer_rd_port = self.answerbuffer.get_port(has_re=True)
        self.specials.answer_wr_port = self.answerbuffer.get_port(write_capable=True)
        self.specials.updatebuffer = Memory(len(update_dat_w), 2**6)
        self.specials.update_rd_port = self.updatebuffer.get_port(has_re=True)
        self.specials.update_wr_port = self.updatebuffer.get_port(write_capable=True)

        self.comb += [
            self.update_wr_port.dat_w.eq(update_dat_w.raw_bits())
        ]

        next_node_idx = Signal(edgeidsize)
        end_node_idx = Signal(edgeidsize)
        last_neighbor = Signal()

        message = Signal(config.addresslayout.payloadsize)
        sender = Signal(config.addresslayout.nodeidsize)
        roundpar = Signal()
        num_neighbors = Signal(edgeidsize)

        current_tag = Signal(6)
        self.comb += If(inject, current_tag.eq(num_injected)).Else(current_tag.eq(self.tags.dout))

        self.num_requests_accepted = Signal(32)
        self.num_hmc_commands_issued = Signal(32)
        self.num_hmc_commands_retired = Signal(32)
        self.num_hmc_responses = Signal(32)

        self.sync += [
            If(hmc_port.cmd_valid & hmc_port.cmd_ready, self.num_hmc_commands_issued.eq(self.num_hmc_commands_issued + 1)),
            If(self.answers.readable & self.answers.re, self.num_hmc_commands_retired.eq(self.num_hmc_commands_retired + 1)),
            If(hmc_port.rd_data_valid & ~hmc_port.dinv, self.num_hmc_responses.eq(self.num_hmc_responses + 1)),
            If(self.valid & self.ack, self.num_requests_accepted.eq(self.num_requests_accepted + 1))
        ]

        self.submodules.fsm = fsm = FSM()
        fsm.act("IDLE", # wait for input
            self.ack.eq(1),
            NextValue(message, self.message_in),
            NextValue(sender, self.sender_in),
            NextValue(roundpar, self.round_in),
            NextValue(num_neighbors, self.num_neighbors),
            If(self.barrier_in,
                NextState("BARRIER")
            ),
            If(self.valid & (self.num_neighbors != 0),
                NextValue(next_node_idx, self.start_idx),
                NextValue(end_node_idx, self.start_idx + (self.num_neighbors << 2)),
                NextState("GET_NEIGHBORS")
            )
        )
        fsm.act("GET_NEIGHBORS",
            hmc_port.cmd_valid.eq(inject | self.tags.readable),
            self.update_wr_port.we.eq(hmc_port.cmd_valid),
            If(hmc_port.cmd_valid & hmc_port.cmd_ready,
                NextValue(next_node_idx, next_node_idx + 16),
                If(next_node_idx + 16 >= end_node_idx,
                    NextState("IDLE")
                )
            )
        )
        fsm.act("BARRIER",
            If(no_tags_inflight & ~self.neighbor_valid,
                NextValue(self.barrier_out, 1),
                NextState("BARRIER_WAIT")
            )
        )
        fsm.act("BARRIER_WAIT",
            If(self.neighbor_ack,
                NextValue(self.barrier_out, 0),
                NextState("IDLE")
            )
        )

        self.sync += If(inject & hmc_port.cmd_ready & hmc_port.cmd_valid,
            num_injected.eq(num_injected + 1)
        )



        self.comb += [
            hmc_port.addr.eq(next_node_idx),
            self.update_wr_port.adr.eq(current_tag),
            update_dat_w.message.eq(message),
            update_dat_w.sender.eq(sender),
            update_dat_w.round.eq(roundpar),
            update_dat_w.num_neighbors.eq(num_neighbors),
            If(next_node_idx + 16 <= end_node_idx,
                update_dat_w.valid.eq(3)
            ).Else(
                update_dat_w.valid.eq(end_node_idx[2:4]-1)
            ),
            no_tags_inflight.eq(self.tags.level == num_injected),
            inject.eq(~num_injected[6]),
            hmc_port.clk.eq(ClockSignal()),
            hmc_port.cmd.eq(0), #`define HMC_CMD_RD 4'b0000
            hmc_port.size.eq(1),
            If(inject, hmc_port.tag.eq(num_injected)).Else(hmc_port.tag.eq(self.tags.dout)),
            self.tags.re.eq(hmc_port.cmd_ready & hmc_port.cmd_valid & ~inject)
        ]

        # receive bursts from HMC - save data, put tag in queue for available answers
        self.comb += [
            self.answer_wr_port.dat_w.eq(hmc_port.rd_data),
            self.answer_wr_port.adr.eq(hmc_port.rd_data_tag),
            self.answer_wr_port.we.eq(hmc_port.rd_data_valid & ~hmc_port.dinv),
            self.answers.din.eq(hmc_port.rd_data_tag),
            self.answers.we.eq(hmc_port.rd_data_valid & ~hmc_port.dinv)
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
            self.get_answer.ack_in.eq(last & self.neighbor_ack)
        ]

        self.sync += [
            If(self.neighbor_valid & self.neighbor_ack,
                If(last,
                    mux.eq(0)
                ).Else(
                    mux.eq(mux + 1)
                )
            )
        ]

        cases = {}
        for i in range(4):
            cases[i] = self.neighbor.eq(self.answer_rd_port.dat_r[i*32:(i+1)*32])
        self.comb += Case(mux, cases).makedefault()


        self.comb += [
            self.neighbor_valid.eq(self.get_answer.valid_out),
            self.message_out.eq(self.get_answer.message_out),
            self.sender_out.eq(self.get_answer.sender_out),
            self.round_out.eq(self.get_answer.round_out),
            self.num_neighbors_out.eq(self.get_answer.num_neighbors_out)
        ]


