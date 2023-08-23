from migen import *

from migen.genlib.fifo import *
from migen.genlib.fsm import *

from core_interfaces import ApplyInterface, Message, _msg_layout
from util.recordfifo import *

from functools import reduce
from operator import and_
import logging

class Barriercounter(Module):
    def __init__(self, config):
        self.apply_interface_in = ApplyInterface(name="barriercounter_in", **config.addresslayout.get_params())
        self.apply_interface_out = ApplyInterface(name="barriercounter_out", **config.addresslayout.get_params())
        self.round_accepting = Signal(config.addresslayout.channel_bits)

    def gen_simulation(self, tb):
        logger = logging.getLogger('sim.barriercounter')
        num_cycles = 0
        round_accepting = 0
        in_q = []
        num_from_pe = [0 for _ in range(tb.config.addresslayout.num_pe)]
        num_expected_from_pe = [0 for _ in range(tb.config.addresslayout.num_pe)]
        barrier_from_pe = [0 for _ in range(tb.config.addresslayout.num_pe)]
        vote_to_halt = 1
        while not (yield tb.global_inactive):
            num_cycles += 1
            if len(in_q) < 10:
                yield self.apply_interface_in.ack.eq(1)
            else:
                yield self.apply_interface_in.ack.eq(0)

            if in_q:
                (barrier, halt, roundpar, dest_id, sender, payload) = in_q[0]
                if not roundpar == round_accepting:
                    logger.warning("{}: Received message of round {} when only accepting round {}".format(num_cycles, roundpar, round_accepting))
                    in_q.pop(0)
                    in_q.append((barrier, halt, roundpar, dest_id, sender, payload))
                from_pe = tb.config.addresslayout.pe_adr(sender)
                if barrier:
                    barrier_from_pe[from_pe] = 1
                    num_expected_from_pe[from_pe] = dest_id
                    if not halt:
                        vote_to_halt = 0
                    for i in range(tb.config.addresslayout.num_pe):
                        if (not barrier_from_pe[i]) or not (num_from_pe[i] == num_expected_from_pe[i]):
                            in_q.pop(0)
                            yield self.apply_interface_out.valid.eq(0)
                            break
                    else:
                        yield self.apply_interface_out.msg.barrier.eq(barrier)
                        yield self.apply_interface_out.msg.halt.eq(vote_to_halt)
                        yield self.apply_interface_out.msg.roundpar.eq(roundpar)
                        yield self.apply_interface_out.msg.dest_id.eq(dest_id)
                        yield self.apply_interface_out.msg.sender.eq(sender)
                        yield self.apply_interface_out.msg.payload.eq(payload)
                        yield self.apply_interface_out.valid.eq(1)
                        vote_to_halt = 1
                else:
                    yield self.apply_interface_out.msg.barrier.eq(barrier)
                    yield self.apply_interface_out.msg.halt.eq(0)
                    yield self.apply_interface_out.msg.roundpar.eq(roundpar)
                    yield self.apply_interface_out.msg.dest_id.eq(dest_id)
                    yield self.apply_interface_out.msg.sender.eq(sender)
                    yield self.apply_interface_out.msg.payload.eq(payload)
                    yield self.apply_interface_out.valid.eq(1)
            else:
                for i in range(tb.config.addresslayout.num_pe):
                    if (not barrier_from_pe[i]) or not (num_from_pe[i] == num_expected_from_pe[i]):
                        yield self.apply_interface_out.valid.eq(0)
                        break
                else:
                    yield self.apply_interface_out.msg.barrier.eq(1)
                    yield self.apply_interface_out.msg.roundpar.eq(round_accepting)
                    yield self.apply_interface_out.msg.dest_id.eq(0)
                    yield self.apply_interface_out.msg.sender.eq(0)
                    yield self.apply_interface_out.msg.payload.eq(0)
                    yield self.apply_interface_out.valid.eq(1)

            yield self.round_accepting.eq(round_accepting)

            yield

            if (yield self.apply_interface_out.valid) and (yield self.apply_interface_out.ack):
                in_q.pop(0)
                if (yield self.apply_interface_out.msg.barrier):
                    num_from_pe = [0 for _ in range(tb.config.addresslayout.num_pe)]
                    num_expected_from_pe = [0 for _ in range(tb.config.addresslayout.num_pe)]
                    barrier_from_pe = [0 for _ in range(tb.config.addresslayout.num_pe)]
                    round_accepting = (round_accepting + 1) % tb.config.addresslayout.num_channels
                else:
                    from_pe = tb.config.addresslayout.pe_adr((yield self.apply_interface_out.msg.sender))
                    num_from_pe[from_pe] += 1

            if (yield self.apply_interface_in.valid) and (yield self.apply_interface_in.ack):
                barrier = (yield self.apply_interface_in.msg.barrier)
                halt = (yield self.apply_interface_in.msg.halt)
                roundpar = (yield self.apply_interface_in.msg.roundpar)
                dest_id = (yield self.apply_interface_in.msg.dest_id)
                sender = (yield self.apply_interface_in.msg.sender)
                payload = (yield self.apply_interface_in.msg.payload)
                in_q.append((barrier, halt, roundpar, dest_id, sender, payload))
