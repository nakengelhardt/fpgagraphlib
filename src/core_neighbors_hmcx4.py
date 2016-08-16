from migen import *
from migen.genlib.fsm import FSM, NextState, NextValue
from migen.genlib.fifo import SyncFIFO
from migen.genlib.roundrobin import *

from functools import reduce
from operator import and_


_data_layout = [
    ("message", "payloadsize"),
    ("sender", "nodeidsize"),
    ("round", 1),
    ("num_neighbors", "edgeidsize"),
    ("from_pe", 2),
    ("valid", 3),
    ("barrier", 1)
]

class BurstDownconverter(Module):
    def __init__(self, update_layout):
        self.update_in = Record(update_layout)
        self.burst_in = Signal(128)
        self.valid_in = Signal()
        self.ack_in = Signal()

        nodeidsize = len(self.update_in.sender)
        edgeidsize = len(self.update_in.num_neighbors)
        payloadsize = len(self.update_in.message)

        self.neighbor = Signal(nodeidsize)
        self.neighbor_valid = Signal()
        self.neighbor_ack = Signal()
        self.message_out = Signal(payloadsize)
        self.sender_out = Signal(nodeidsize)
        self.round_out = Signal()
        self.num_neighbors_out = Signal(edgeidsize)
        self.barrier_out = Signal()

        update_reg = Record(update_layout)
        burst_reg = Signal(128)
        valid_reg = Signal()
        ack = Signal()

        self.sync += If(ack,
            update_reg.raw_bits().eq(self.update_in.raw_bits()),
            burst_reg.eq(self.burst_in),
            valid_reg.eq(self.valid_in)
        )
        self.comb += self.ack_in.eq(ack | ~valid_reg)

        mux = Signal(3)
        last = Signal()
        self.comb += [
            last.eq(mux == (update_reg.valid-1)),
            ack.eq( (last & self.neighbor_ack) | ~valid_reg )
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
            cases[i] = self.neighbor.eq(burst_reg[i*32:(i+1)*32])
        self.comb += Case(mux, cases).makedefault()

        # output
        self.comb += [
            self.neighbor_valid.eq(valid_reg & ~update_reg.barrier),
            self.message_out.eq(update_reg.message),
            self.sender_out.eq(update_reg.sender),
            self.round_out.eq(update_reg.round),
            self.num_neighbors_out.eq(update_reg.num_neighbors),
            self.barrier_out.eq(valid_reg & update_reg.barrier)
        ]


class Neighborsx4(Module):
    def __init__(self, pe_id, config, adj_val=None, edge_data=None, hmc_port=None):
        nodeidsize = config.addresslayout.nodeidsize
        edgeidsize = config.addresslayout.edgeidsize
        payloadsize = config.addresslayout.payloadsize

        update_layout = set_layout_parameters(_data_layout, payloadsize=config.addresslayout.payloadsize, nodeidsize=config.addresslayout.nodeidsize, edgeidsize=config.addresslayout.edgeidsize)

        # input
        self.start_idx = [Signal(edgeidsize) for _ in range(4)]
        self.num_neighbors = [Signal(edgeidsize) for _ in range(4)]
        self.valid = [Signal() for _ in range(4)]
        self.ack = [Signal() for _ in range(4)]
        self.barrier_in = [Signal() for _ in range(4)]
        self.message_in = [Signal(payloadsize) for _ in range(4)]
        self.sender_in = [Signal(nodeidsize) for _ in range(4)]
        self.round_in = [Signal() for _ in range(4)]

        # output
        self.neighbor = [Signal(nodeidsize) for _ in range(4)]
        self.neighbor_valid = [Signal() for _ in range(4)]
        self.neighbor_ack = [Signal() for _ in range(4)]
        self.barrier_out = [Signal() for _ in range(4)]
        self.message_out = [Signal(payloadsize) for _ in range(4)]
        self.sender_out = [Signal(nodeidsize) for _ in range(4)]
        self.round_out = [Signal() for _ in range(4)]
        self.num_neighbors_out = [Signal(edgeidsize) for _ in range(4)]

        ###

        assert(edgeidsize == 32)

        #input

        self.fifos = [SyncFIFO(2*edgeidsize+nodeidsize+payloadsize+2, 8) for _ in range(4)]
        self.submodules += self.fifos

        for i in range(4):
            self.comb += [
                self.fifos[i].we.eq(self.valid[i] | self.barrier_in[i]),
                self.ack[i].eq(self.fifos[i].writable),
                self.fifos[i].din.eq(Cat(self.start_idx[i], self.num_neighbors[i], self.sender_in[i], self.message_in[i], self.barrier_in[i], self.round_in[i]))
            ]

        array_data = Array(fifo.dout for fifo in self.fifos)
        array_re = Array(fifo.re for fifo in self.fifos)
        array_readable = Array(fifo.readable for fifo in self.fifos)


        chosen_start_idx = Signal(edgeidsize)
        chosen_num_neighbors = Signal(edgeidsize)
        chosen_sender_in = Signal(nodeidsize)
        chosen_message_in = Signal(payloadsize)
        chosen_barrier_in = Signal()
        chosen_round_in = Signal()
        chosen_valid = Signal()
        chosen_ack = Signal()
        chosen_from_pe = Signal(2)
        tmp_barrier = Signal()

        self.submodules.roundrobin = RoundRobin(4, switch_policy=SP_CE)

        self.comb += [
            Cat(chosen_start_idx, chosen_num_neighbors, chosen_sender_in, chosen_message_in, tmp_barrier, chosen_round_in).eq(array_data[self.roundrobin.grant]),
            chosen_valid.eq(array_readable[self.roundrobin.grant] & ~tmp_barrier),
            chosen_from_pe.eq(self.roundrobin.grant),
            chosen_barrier_in.eq(tmp_barrier & array_readable[self.roundrobin.grant])
        ]
        self.comb += [
            array_re[self.roundrobin.grant].eq(chosen_ack),
            [self.roundrobin.request[i].eq(array_readable[i]) for i in range(len(self.fifos))],
            self.roundrobin.ce.eq(chosen_ack)
        ]


        num_injected = Signal(7)
        inject = Signal()

        no_tags_inflight = Signal()

        if not hmc_port:
            hmc_port = config.platform.getHMCPort(0)


        update_dat_r = Record(update_layout)
        update_dat_w = Record(update_layout)

        self.submodules.tags = SyncFIFO(6, 2**6)
        self.submodules.answers = SyncFIFO(6, 2**6)
        self.specials.answerbuffer = Memory(128, 2**6)
        self.specials.answer_rd_port = self.answerbuffer.get_port(has_re=True)
        self.specials.answer_wr_port = self.answerbuffer.get_port(write_capable=True)
        self.specials.updatebuffer = Memory(len(update_dat_w), 2**6)
        self.specials.update_rd_port = self.updatebuffer.get_port(has_re=True)
        self.specials.update_wr_port = self.updatebuffer.get_port(write_capable=True)

        self.comb += [
            update_dat_r.raw_bits().eq(self.update_rd_port.dat_r),
            self.update_wr_port.dat_w.eq(update_dat_w.raw_bits())
        ]

        next_node_idx = Signal(edgeidsize)
        end_node_idx = Signal(edgeidsize)
        last_neighbor = Signal()

        message = Signal(payloadsize)
        sender = Signal(nodeidsize)
        roundpar = Signal()
        num_neighbors = Signal(edgeidsize)

        current_tag = Signal(6)
        self.comb += If(inject, current_tag.eq(num_injected)).Else(current_tag.eq(self.tags.dout))

        self.num_requests_accepted = Signal(32)
        self.num_hmc_commands_issued = Signal(32)
        self.num_hmc_commands_retired = Signal(32)
        self.num_hmc_responses = Signal(32)
        self.num_reqs = [Signal(32) for _ in range(4)]
        self.wrongs = [Signal(32) for _ in range(4)]

        self.sync += [
            If(hmc_port.cmd_valid & hmc_port.cmd_ready, self.num_hmc_commands_issued.eq(self.num_hmc_commands_issued + 1)),
            If(self.answers.readable & self.answers.re, self.num_hmc_commands_retired.eq(self.num_hmc_commands_retired + 1)),
            If(hmc_port.rd_data_valid & ~hmc_port.dinv, self.num_hmc_responses.eq(self.num_hmc_responses + 1)),
            If(chosen_valid & chosen_ack, self.num_requests_accepted.eq(self.num_requests_accepted + 1)),
            [If(self.valid[i] & self.ack[i], self.num_reqs[i].eq(self.num_reqs[i] + 1)) for i in range(4)],
            [If(self.neighbor_valid[i] & self.barrier_out[i], self.wrongs[i].eq(self.wrongs[i] + 1)) for i in range(4)],
        ]

        from_pe = Signal(2)
        barrier_requested = Signal()
        barrier_received = Signal()
        flushed = Signal()

        self.submodules.fsm = fsm = FSM()
        fsm.act("IDLE", # wait for input
            chosen_ack.eq(1),
            NextValue(message, chosen_message_in),
            NextValue(sender, chosen_sender_in),
            NextValue(roundpar, chosen_round_in),
            NextValue(num_neighbors, chosen_num_neighbors),
            NextValue(from_pe, chosen_from_pe),
            If(chosen_barrier_in,
                NextState("BARRIER")
            ),
            If(chosen_valid & (chosen_num_neighbors != 0),
                NextValue(next_node_idx, chosen_start_idx),
                NextValue(end_node_idx, chosen_start_idx + (chosen_num_neighbors << 2)),
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
            If(flushed,
                NextState("BARRIER_WAIT")
            )
        )
        fsm.act("BARRIER_WAIT",
            barrier_requested.eq(1),
            If(barrier_received,
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
            update_dat_w.from_pe.eq(from_pe),
            If(next_node_idx + 16 <= end_node_idx,
                update_dat_w.valid.eq(4)
            ).Else(
                update_dat_w.valid.eq(end_node_idx[2:4])
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

        # get one answer
        valid0 = Signal()
        ack0 = Signal()

        self.comb += [
            self.answers.re.eq(ack0),
            self.answer_rd_port.adr.eq(self.answers.dout),
            self.answer_rd_port.re.eq(ack0),
            self.update_rd_port.adr.eq(self.answers.dout),
            self.update_rd_port.re.eq(ack0),
            self.tags.din.eq(self.answers.dout),
            self.tags.we.eq(self.answers.readable & ack0)
        ]

        self.sync += If(ack0,
            valid0.eq(self.answers.readable)
        )

        update1 = Record(update_layout)
        burst1 = Signal(128)
        valid1 = Signal()
        ack1 = Signal()

        self.comb += [
            ack0.eq(ack1 | ~valid1),
            If(barrier_requested,
                barrier_received.eq(ack0)
            ),
            flushed.eq(no_tags_inflight & ~valid0 & ~valid1)
        ]

        self.sync += If(ack0,
            If(barrier_requested,
                update1.message.eq(message),
                update1.sender.eq(sender),
                update1.round.eq(roundpar),
                update1.num_neighbors.eq(num_neighbors),
                update1.from_pe.eq(from_pe),
                update1.valid.eq(1),
                update1.barrier.eq(1),
                burst1.eq(0),
                valid1.eq(1)
            ).Else(
                update1.raw_bits().eq(self.update_rd_port.dat_r),
                burst1.eq(self.answer_rd_port.dat_r),
                valid1.eq(valid0)
            )
        )

        # distribute to correct scatter

        downconverter = [BurstDownconverter(update_layout) for _ in range(4)]
        self.submodules += downconverter
        dc_valid_array = Array(downconverter[i].valid_in for i in range(4))
        dc_ack_array = Array(downconverter[i].ack_in for i in range(4))

        self.comb += [
            [downconverter[i].update_in.raw_bits().eq(update1.raw_bits()) for i in range(4)],
            [downconverter[i].burst_in.eq(burst1) for i in range(4)],
            dc_valid_array[update1.from_pe].eq(valid1),
            ack1.eq(dc_ack_array[update1.from_pe])
        ]

        self.comb += [
            [self.neighbor[i].eq(downconverter[i].neighbor) for i in range(4)],
            [self.neighbor_valid[i].eq(downconverter[i].neighbor_valid) for i in range(4)],
            [self.message_out[i].eq(downconverter[i].message_out) for i in range(4)],
            [self.sender_out[i].eq(downconverter[i].sender_out) for i in range(4)],
            [self.round_out[i].eq(downconverter[i].round_out) for i in range(4)],
            [self.num_neighbors_out[i].eq(downconverter[i].num_neighbors_out) for i in range(4)],
            [self.barrier_out[i].eq(downconverter[i].barrier_out) for i in range(4)],
            [downconverter[i].neighbor_ack.eq(self.neighbor_ack[i]) for i in range(4)]
        ]
