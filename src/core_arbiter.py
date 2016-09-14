from migen import *

from migen.genlib.roundrobin import *
from migen.genlib.fifo import *

from core_interfaces import ApplyInterface, Message, _msg_layout

from functools import reduce
from operator import and_
import logging

class Arbiter(Module):
    def __init__(self, pe_id, config, fifos):
        addresslayout = config.addresslayout
        nodeidsize = addresslayout.nodeidsize
        num_pe = addresslayout.num_pe
        self.pe_id = pe_id

        # output
        self.apply_interface = ApplyInterface(**addresslayout.get_params())

        # input override for injecting the message starting the computation
        self.start_message = ApplyInterface(name="start_message", **addresslayout.get_params())
        self.start_message.select = Signal()

        self.fifos = fifos

        self.submodules.roundrobin = RoundRobin(num_pe, switch_policy=SP_CE)

        # arrays for choosing incoming fifo to use
        array_data = Array(fifo.dout.raw_bits() for fifo in fifos)
        array_re = Array(fifo.re for fifo in fifos)
        array_readable = Array(fifo.readable for fifo in fifos)
        array_barrier = Array(fifo.dout.barrier for fifo in fifos)
        array_round = Array(fifo.dout.roundpar for fifo in fifos)

        # chosen incoming message
        self.stage1 = stage1 = ApplyInterface(name="stage1", **addresslayout.get_params())

        # even/odd storage queues
        # TODO: not using message contents, switch to SyncFIFO?
        self.submodules.outfifo_even = SyncFIFOBuffered(layout_len(set_layout_parameters(_msg_layout,**addresslayout.get_params())), depth=128)
        self.submodules.outfifo_odd  = SyncFIFOBuffered(layout_len(set_layout_parameters(_msg_layout,**addresslayout.get_params())), depth=128)

        array_outfifo_din = Array([self.outfifo_even.din, self.outfifo_odd.din])
        array_outfifo_writable = Array([self.outfifo_even.writable, self.outfifo_odd.writable])
        array_outfifo_we = Array([self.outfifo_even.we, self.outfifo_odd.we])

        array_outfifo_dout = Array([self.outfifo_even.dout, self.outfifo_odd.dout])
        array_outfifo_readable = Array([self.outfifo_even.readable, self.outfifo_odd.readable])
        array_outfifo_re = Array([self.outfifo_even.re, self.outfifo_odd.re])

        self.sync += [
            If(stage1.ack,
                stage1.msg.raw_bits().eq(array_data[self.roundrobin.grant]),
                stage1.valid.eq(array_readable[self.roundrobin.grant])
            )
        ]

        self.comb += [
            array_re[self.roundrobin.grant].eq(stage1.ack),
            [self.roundrobin.request[i].eq(array_readable[i] & array_outfifo_writable[array_round[i]]) for i in range(num_pe)],
            self.roundrobin.ce.eq(stage1.ack)
        ]

        # update barrier counter
        self.stage2 = stage2 = ApplyInterface(name="stage2", **addresslayout.get_params())

        self.barrier_from_pe = barrier_from_pe = Array(Signal() for _ in range(num_pe))
        self.num_from_pe = num_from_pe = Array(Array(Signal(nodeidsize) for _ in range(2)) for _ in range(num_pe))
        self.num_expected_from_pe = num_expected_from_pe = Array(Array(Signal(nodeidsize) for _ in range(2)) for _ in range(num_pe))
        self.all_from_pe = Array(Array(Signal() for _ in range (num_pe)) for _ in range(2))
        self.all_messages_recvd = Signal()
        self.all_barriers_recvd = all_barriers_recvd = Signal()
        self.round_collecting = Signal()
        self.barrier_reached = Signal()
        self.comb += [
            all_barriers_recvd.eq(reduce(and_, barrier_from_pe)),
            self.all_messages_recvd.eq(reduce(and_, self.all_from_pe[self.round_collecting])),
            self.barrier_reached.eq(all_barriers_recvd & self.all_messages_recvd)
        ]

        self.sync += [
            If(stage1.valid & stage1.ack,
                If(stage1.msg.barrier,
                    # all_barriers_recvd will be 1 while stage2 is barrier
                    barrier_from_pe[addresslayout.pe_adr(stage1.msg.sender)].eq(1),
                    num_expected_from_pe[addresslayout.pe_adr(stage1.msg.sender)][stage1.msg.roundpar].eq(stage1.msg.dest_id)
                ).Else(
                    num_from_pe[addresslayout.pe_adr(stage1.msg.sender)][stage1.msg.roundpar].eq(num_from_pe[addresslayout.pe_adr(stage1.msg.sender)][stage1.msg.roundpar] + 1)
                )
            ),
            [self.all_from_pe[i][j].eq(num_from_pe[j][i] == num_expected_from_pe[j][i]) for i in range(2) for j in range(num_pe)]
        ]

        self.sync += [
            If(stage2.ack,
                stage2.msg.raw_bits().eq(stage1.msg.raw_bits()),
                stage2.valid.eq(stage1.valid)
            ),
            If(self.barrier_reached & stage2.ack,
                [barrier_from_pe[i].eq(0) for i in range(num_pe)],
                [num_from_pe[i][stage2.msg.roundpar].eq(0) for i in range(num_pe)],
                self.round_collecting.eq(~self.round_collecting)
            )
        ]

        self.comb += [
            stage1.ack.eq(stage2.ack & ~self.barrier_reached)
        ]

        # sort messages into fifos
        barrier_message_const = Message(**addresslayout.get_params())
        self.comb += [
            barrier_message_const.barrier.eq(1),
            barrier_message_const.roundpar.eq(self.round_collecting),
            If(self.barrier_reached,
                self.outfifo_even.din.eq(barrier_message_const.raw_bits()),
                self.outfifo_odd.din.eq(barrier_message_const.raw_bits()),
                stage2.ack.eq(array_outfifo_writable[self.round_collecting]),
                array_outfifo_we[self.round_collecting].eq(1),
            ).Else(
                self.outfifo_even.din.eq(stage2.msg.raw_bits()),
                self.outfifo_odd.din.eq(stage2.msg.raw_bits()),
                stage2.ack.eq(array_outfifo_writable[stage2.msg.roundpar] & ~ self.barrier_reached),
                array_outfifo_we[stage2.msg.roundpar].eq(stage2.valid & ~stage2.msg.barrier),
            )
        ]

        # mux between outfifos and init interface
        apply_interface_internal = ApplyInterface(name="apply_interface_internal", **addresslayout.get_params())
        current_round = Signal()

        self.comb += [
            apply_interface_internal.msg.raw_bits().eq(array_outfifo_dout[current_round]),
            apply_interface_internal.valid.eq(array_outfifo_readable[current_round]),
            array_outfifo_re[current_round].eq(apply_interface_internal.ack)
        ]

        self.sync += \
            If(apply_interface_internal.valid & apply_interface_internal.ack & apply_interface_internal.msg.barrier,
                current_round.eq(~current_round)
            )

        self.comb += \
            If(self.start_message.select,
                self.start_message.connect(self.apply_interface)
            ).Else(
                apply_interface_internal.connect(self.apply_interface)
            )


    def gen_selfcheck(self, tb):
        logger = logging.getLogger("simulation.arbiter" + str(self.pe_id))
        level = 0
        num_cycles = 0
        last_valid = 0
        from_pe_since_last_barrier = [[0 for _ in range(tb.addresslayout.num_pe)] for _ in range(2)]
        while not (yield tb.global_inactive):
            num_cycles += 1
            if (yield self.stage1.valid) and (yield self.stage1.ack):
                sender_pe = (yield tb.addresslayout.pe_adr(self.stage1.msg.sender))
                roundpar = (yield self.stage1.msg.roundpar)
                if (yield self.stage1.msg.barrier):
                    if roundpar != (yield self.round_collecting):
                        logger.warning("{}: received barrier for round {} but currently waiting for {}".format(num_cycles, roundpar, (yield self.round_collecting)))
                    if from_pe_since_last_barrier[roundpar][sender_pe] != (yield self.stage1.msg.dest_id):
                        logger.warning("{}: received {} messages from PE {} but barrier says {} were sent".format(num_cycles, from_pe_since_last_barrier[roundpar][sender_pe], sender_pe, (yield self.stage1.msg.dest_id)))
                    from_pe_since_last_barrier[roundpar][sender_pe] = 0
                    logger.debug("{}: Barrier (round {}) from PE {}".format(num_cycles, (yield self.stage1.msg.roundpar), sender_pe))
                else:
                    if from_pe_since_last_barrier[roundpar][sender_pe] != (yield self.num_from_pe[sender_pe][roundpar]):
                        logger.warning("{}: received {} messages but count is {}".format(num_cycles, from_pe_since_last_barrier[roundpar][sender_pe], (yield self.num_from_pe[sender_pe][roundpar])))
                    from_pe_since_last_barrier[roundpar][sender_pe] += 1
            if (yield self.stage2.ack) and (yield self.stage2.msg.barrier):
                if (yield self.all_barriers_recvd):
                    logger.debug("{}: All barriers found".format(num_cycles))
                    roundpar = (yield self.stage2.msg.roundpar)
                    for i in range(tb.addresslayout.num_pe):
                        if (yield self.num_from_pe[i][roundpar]) != (yield self.num_expected_from_pe[i][roundpar]):
                            logger.warning("{}: Not yet received all messages from PE {}".format(num_cycles, i))
                elif last_valid:
                    if not (yield self.barrier_from_pe[tb.addresslayout.pe_adr(self.stage2.msg.sender)]):
                        logger.warning("{}: Barrier lost".format(num_cycles))
                    else:
                        logger.debug("{}: Barrier saved".format(num_cycles))
            last_valid = (yield self.stage1.valid)
            if (yield self.apply_interface.valid) and (yield self.apply_interface.ack):
                if (yield self.apply_interface.msg.barrier):
                    level += 1
                    logger.debug("{}: Barrier passed to apply".format(num_cycles))
                else:
                    if level % 2 == (yield self.apply_interface.msg.roundpar):
                        logger.warning("{}: received message's parity ({}) does not match current round ({})".format(num_cycles, (yield self.apply_interface.msg.roundpar), level))
            yield
