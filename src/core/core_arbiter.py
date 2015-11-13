from migen import *

from migen.genlib.fifo import SyncFIFO
from migen.genlib.roundrobin import *

from core_interfaces import ApplyInterface, Message

from functools import reduce
from operator import and_

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

        barrier_reached = Signal()
        self.comb += barrier_reached.eq(reduce(and_, array_barrier) & reduce(and_, array_readable))

        self.comb += If( self.start_message.select, # override
                        self.apply_interface.msg.raw_bits().eq(self.start_message.msg.raw_bits()),
                        self.apply_interface.valid.eq(self.start_message.valid),
                        self.start_message.ack.eq(self.apply_interface.ack),
                        self.roundrobin.ce.eq(0)
                     ).Elif( barrier_reached,
                        self.apply_interface.msg.barrier.eq(1),
                        self.apply_interface.valid.eq(1),
                        [array_re[i].eq(self.apply_interface.ack) for i in range(len(fifos))]
                     ).Else( # normal roundrobin
                        self.apply_interface.msg.raw_bits().eq(array_data[self.roundrobin.grant]),
                        self.apply_interface.valid.eq(array_readable[self.roundrobin.grant] & ~ array_barrier[self.roundrobin.grant]),
                        array_re[self.roundrobin.grant].eq(self.apply_interface.ack & ~ array_barrier[self.roundrobin.grant]), 
                        [self.roundrobin.request[i].eq(array_readable[i] & ~ array_barrier[i]) for i in range(len(fifos))], 
                        self.roundrobin.ce.eq(self.apply_interface.ack)
                     )

    def gen_selfcheck(self, tb, quiet=True):
        level = 0
        num_cycles = 0
        while not (yield tb.global_inactive):
            num_cycles += 1
            if (yield self.apply_interface.msg.barrier) and (yield self.apply_interface.ack):
                level += 1
                if not (yield self.start_message.select):
                    for fifo in self.fifos:
                        if not ((yield fifo.dout.barrier) and (yield fifo.readable) and (yield fifo.re)):
                            print("{}\tWarning: barrier passed and not withdrawn correctly from fifo {}".format(num_cycles, self.fifos.index(fifo)))
            yield