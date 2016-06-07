from migen import *

from migen.genlib.roundrobin import *
from recordfifo import RecordFIFO

from core_interfaces import ApplyInterface, Message

from functools import reduce
from operator import and_
import logging

class Arbiter(Module):
    def __init__(self, config, fifos):
        addresslayout = config.addresslayout
        nodeidsize = addresslayout.nodeidsize
        num_pe = addresslayout.num_pe

        # output
        self.apply_interface = ApplyInterface(**addresslayout.get_params())

        # input override for injecting the message starting the computation
        self.start_message = ApplyInterface(**addresslayout.get_params())
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
        self.stage1 = stage1 = ApplyInterface(**addresslayout.get_params())

        # even/odd storage queues
        # TODO: not using message contents, switch to SyncFIFO?
        self.submodules.outfifo_even = RecordFIFO(layout=Message(**addresslayout.get_params()).layout, depth=128)
        self.submodules.outfifo_odd  = RecordFIFO(layout=Message(**addresslayout.get_params()).layout, depth=128)

        array_outfifo_din = Array([self.outfifo_even.din.raw_bits(), self.outfifo_odd.din.raw_bits()])
        array_outfifo_writable = Array([self.outfifo_even.writable, self.outfifo_odd.writable])
        array_outfifo_we = Array([self.outfifo_even.we, self.outfifo_odd.we])

        array_outfifo_dout = Array([self.outfifo_even.dout.raw_bits(), self.outfifo_odd.dout.raw_bits()])
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
        self.stage2 = stage2 = ApplyInterface(**addresslayout.get_params())

        self.barrier_from_pe = barrier_from_pe = Array(Signal() for _ in range(num_pe))
        self.barrier_reached = barrier_reached = Signal()
        self.comb += barrier_reached.eq(reduce(and_, barrier_from_pe))

        self.sync += [
            If(stage2.ack,
                If(barrier_reached,
                    [barrier_from_pe[i].eq(0) for i in range(num_pe)]
                ).Else(
                    barrier_from_pe[addresslayout.pe_adr(stage1.msg.sender)].eq(barrier_from_pe[addresslayout.pe_adr(stage1.msg.sender)] | (stage1.msg.barrier & stage1.valid))
                    # barrier_reached will be 1 while stage2 is barrier
                    #TODO: verify this in gen_selfcheck
                ),
                stage2.msg.raw_bits().eq(stage1.msg.raw_bits()),
                stage2.valid.eq(stage1.valid)
            )
        ]

        self.comb += [
            stage1.ack.eq(stage2.ack)
        ]

        # sort messages into fifos
        self.comb += [
            self.outfifo_even.din.raw_bits().eq(stage2.msg.raw_bits()),
            self.outfifo_odd.din.raw_bits().eq(stage2.msg.raw_bits()),
            stage2.ack.eq(array_outfifo_writable[stage2.msg.roundpar]),
            array_outfifo_we[stage2.msg.roundpar].eq(stage2.valid & (~stage2.msg.barrier | barrier_reached)),
        ]

        # mux between outfifos and init interface
        apply_interface_internal = ApplyInterface(**addresslayout.get_params())
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
        logger = logging.getLogger("simulation.arbiter")
        level = 0
        num_cycles = 0
        last_valid = 0
        while not (yield tb.global_inactive):
            num_cycles += 1
            if (yield self.stage1.valid) and (yield self.stage1.ack) and (yield self.stage1.msg.barrier):
                logger.debug("{}: Barrier (round {}) from PE {}".format(num_cycles, (yield self.stage1.msg.roundpar), (yield tb.addresslayout.pe_adr(self.stage1.msg.sender))))
            if (yield self.stage2.ack) and (yield self.stage2.msg.barrier):
                if (yield self.stage2.valid):
                    logger.debug("{}: All barriers found".format(num_cycles))
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
