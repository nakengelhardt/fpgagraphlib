from migen import *

from migen.genlib.fifo import *

from core_interfaces import ApplyInterface, Message, _msg_layout
from core_barriercounter import Barriercounter

from functools import reduce
from operator import and_
import logging

class Arbiter(Module):
    def __init__(self, pe_id, config):
        addresslayout = config.addresslayout
        nodeidsize = addresslayout.nodeidsize
        num_pe = addresslayout.num_pe
        self.pe_id = pe_id

        # input (n channels)
        self.apply_interface_in = [ApplyInterface(**addresslayout.get_params()) for _ in range(config.addresslayout.num_channels)]

        # output
        self.apply_interface_out = ApplyInterface(**addresslayout.get_params())

        # input override for injecting the message starting the computation
        self.start_message = ApplyInterface(name="start_message", **addresslayout.get_params())
        self.start_message.select = Signal()

        # buffer inputs
        self.submodules.channel_buffers = [SyncFIFOBuffered(layout_len(set_layout_parameters(_msg_layout,**addresslayout.get_params())), depth=128) for _ in range(config.addresslayout.num_channels)]

        array_channel_buffer_dout = Array([fifo.dout for fifo in self.channel_buffers])
        array_channel_buffer_readable = Array([fifo.readable for fifo in self.channel_buffers])
        array_channel_buffer_re = Array([fifo.re for fifo in self.channel_buffers])

        self.comb += [
            [self.channel_buffers[i].din.eq(self.apply_interface_in[i].msg.raw_bits()) for i in range(config.addresslayout.num_channels)],
            [self.channel_buffers[i].we.eq(self.apply_interface_in[i].valid) for i in range(config.addresslayout.num_channels)],
            [self.apply_interface_in[i].ack.eq(self.channel_buffers[i].writable) for i in range(config.addresslayout.num_channels)]
        ]

        apply_interface_internal = ApplyInterface(name="apply_interface_internal", **addresslayout.get_params())

        self.submodules.barriercounter = Barriercounter(config)

        current_round = Signal(config.addresslayout.channel_bits)

        self.comb += [
            self.barriercounter.apply_interface_in.msg.raw_bits().eq(array_channel_buffer_dout[current_round]),
            self.barriercounter.apply_interface_in.valid.eq(array_channel_buffer_readable[current_round]),
            array_channel_buffer_re[current_round].eq(self.barriercounter.apply_interface_in.ack),
            apply_interface_internal.msg.raw_bits().eq(self.barriercounter.apply_interface_out.msg.raw_bits()),
            apply_interface_internal.valid.eq(self.barriercounter.apply_interface_out.valid),
            self.barriercounter.apply_interface_out.ack.eq(apply_interface_internal.ack)
        ]

        self.sync += \
            If(self.barriercounter.change_rounds,
                If(current_round < config.addresslayout.num_channels - 1,
                    current_round.eq(current_round + 1)
                ).Else(
                    current_round.eq(0)
                )
            )

        self.submodules.outfifo = SyncFIFO(layout_len(set_layout_parameters(_msg_layout,**addresslayout.get_params())), depth=2)

        # choose between init and regular message channel
        self.comb += [
            If(self.start_message.select,
                self.outfifo.din.eq(self.start_message.msg.raw_bits()),
                self.outfifo.we.eq(self.start_message.valid),
                self.start_message.ack.eq(self.outfifo.writable)
            ).Else(
                self.outfifo.din.eq(apply_interface_internal.msg.raw_bits()),
                self.outfifo.we.eq(apply_interface_internal.valid),
                apply_interface_internal.ack.eq(self.outfifo.writable)
            ),
            self.apply_interface_out.msg.raw_bits().eq(self.outfifo.dout),
            self.apply_interface_out.valid.eq(self.outfifo.readable),
            self.outfifo.re.eq(self.apply_interface_out.ack)
        ]


    def gen_selfcheck(self, tb):
        logger = logging.getLogger("simulation.arbiter" + str(self.pe_id))
        level = 0
        num_cycles = 0

        while not (yield tb.global_inactive):
            num_cycles += 1

            if (yield self.apply_interface_out.valid) and (yield self.apply_interface_out.ack):
                if (yield self.apply_interface_out.msg.barrier):
                    level += 1
                    logger.debug("{}: Barrier passed to apply".format(num_cycles))
                else:
                    if level % 2 == (yield self.apply_interface_out.msg.roundpar):
                        logger.warning("{}: received message's parity ({}) does not match current round ({})".format(num_cycles, (yield self.apply_interface_out.msg.roundpar), level))
            yield
