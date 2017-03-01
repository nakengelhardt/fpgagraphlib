from migen import *

from core_interfaces import ApplyInterface, NetworkInterface
from sim_barriercounter import Barriercounter

import logging

class Arbiter(Module):
    def __init__(self, pe_id, config):
        addresslayout = config.addresslayout
        nodeidsize = addresslayout.nodeidsize
        num_pe = addresslayout.num_pe
        self.pe_id = pe_id

        # input (n channels)
        self.apply_interface_in = ApplyInterface(name="arbiter_in", **addresslayout.get_params())

        # output
        self.apply_interface_out = ApplyInterface(name="arbiter_out", **addresslayout.get_params())

        # input override for injecting the message starting the computation
        self.start_message = ApplyInterface(name="start_message", **addresslayout.get_params())
        self.start_message.select = Signal()

        self.submodules.barriercounter = Barriercounter(config)
        self.current_round = Signal(config.addresslayout.channel_bits)

        self.comb += [
            self.barriercounter.apply_interface_in.msg.raw_bits().eq(self.apply_interface_in.msg.raw_bits()),
            self.barriercounter.apply_interface_in.valid.eq(self.apply_interface_in.valid),
            self.apply_interface_in.ack.eq(self.barriercounter.apply_interface_in.ack),
            self.current_round.eq(self.barriercounter.round_accepting)
        ]

        # choose between init and regular message channel
        self.comb += \
            If(self.start_message.select,
                self.start_message.connect(self.apply_interface_out)
            ).Else(
                self.barriercounter.apply_interface_out.connect(self.apply_interface_out)
            )
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



class Network(Module):
    def __init__(self, config):
        num_pe = config.addresslayout.num_pe
        num_nodes_per_pe = config.addresslayout.num_nodes_per_pe

        self.apply_interface = [ApplyInterface(name="network_out", **config.addresslayout.get_params()) for _ in range(num_pe)]
        self.network_interface = [NetworkInterface(name="network_in", **config.addresslayout.get_params()) for _ in range(num_pe)]

        self.submodules.arbiter = [Arbiter(sink, config) for sink in range(num_pe)]
        self.comb += [a.apply_interface_out.connect(self.apply_interface[i]) for i,a in enumerate(self.arbiter)]

    def gen_simulation(self, tb):
        messages = [[list() for _ in range(tb.config.addresslayout.num_channels)] for _ in range(tb.config.addresslayout.num_pe)]
        rnd = [0 for _ in range(tb.config.addresslayout.num_channels)]
        while not (yield tb.global_inactive):
            for i in range(tb.config.addresslayout.num_pe):
                yield self.network_interface[i].ack.eq(1)

                rnd[i] = (yield self.arbiter[i].current_round)
                if len(messages[i][rnd[i]]) > 0:
                    msg = messages[i][rnd[i]][0]
                    yield self.arbiter[i].apply_interface_in.valid.eq(1)
                    yield self.arbiter[i].apply_interface_in.msg.raw_bits().eq(msg)
                else:
                    yield self.arbiter[i].apply_interface_in.valid.eq(0)
            yield

            for i in range(tb.config.addresslayout.num_pe):
                if (yield self.network_interface[i].valid):
                    msg = (yield self.network_interface[i].msg.raw_bits())
                    dest_pe = (yield self.network_interface[i].dest_pe)
                    roundpar = (yield self.network_interface[i].msg.roundpar)
                    messages[dest_pe][roundpar].append(msg)

                if (yield self.arbiter[i].apply_interface_in.valid) and (yield self.arbiter[i].apply_interface_in.ack):
                    messages[i][rnd[i]].pop(0)
