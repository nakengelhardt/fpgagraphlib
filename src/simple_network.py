from migen import *

from migen.genlib.roundrobin import *
from util.recordfifo import RecordFIFO

from core_interfaces import ApplyInterface, Message, NetworkInterface

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

        self.submodules.outfifo = RecordFIFO(layout=Message(**addresslayout.get_params()).layout, depth=8)


        self.comb += If( self.start_message.select, # override
                        self.outfifo.din.raw_bits().eq(self.start_message.msg.raw_bits()),
                        self.outfifo.we.eq(self.start_message.valid),
                        self.start_message.ack.eq(self.outfifo.writable),
                        self.roundrobin.ce.eq(0)
                     ).Elif( barrier_reached,
                        self.outfifo.din.barrier.eq(1),
                        self.outfifo.we.eq(1),
                        [array_re[i].eq(self.outfifo.writable) for i in range(len(fifos))]
                     ).Else( # normal roundrobin
                        self.outfifo.din.raw_bits().eq(array_data[self.roundrobin.grant]),
                        self.outfifo.we.eq(array_readable[self.roundrobin.grant] & ~ array_barrier[self.roundrobin.grant]),
                        array_re[self.roundrobin.grant].eq(self.outfifo.writable & ~ array_barrier[self.roundrobin.grant]),
                        [self.roundrobin.request[i].eq(array_readable[i] & ~ array_barrier[i]) for i in range(len(fifos))],
                        self.roundrobin.ce.eq(self.outfifo.writable)
                     )

        self.comb += [
            self.apply_interface.msg.raw_bits().eq(self.outfifo.dout.raw_bits()),
            self.apply_interface.valid.eq(self.outfifo.readable),
            self.outfifo.re.eq(self.apply_interface.ack)
        ]



    def gen_selfcheck(self, tb, quiet=True):
        level = 0
        num_cycles = 0
        while not (yield tb.global_inactive):
            num_cycles += 1
            if (yield self.outfifo.writable) and (yield self.outfifo.we):
                if (yield self.outfifo.din.barrier):
                    level += 1
                    if not (yield self.start_message.select):
                        for fifo in self.fifos:
                            if not ((yield fifo.dout.barrier) and (yield fifo.readable) and (yield fifo.re)):
                                print("{}\tWarning: barrier passed and not withdrawn correctly from fifo {}".format(num_cycles, self.fifos.index(fifo)))
                else:
                    if level % 2 == (yield self.outfifo.din.roundpar):
                        print("{}\tWarning: received message's parity ({}) does not match current round ({})".format(num_cycles, (yield self.outfifo.din.roundpar), level))
            yield

class Network(Module):
    def __init__(self, config):
        num_pe = config.addresslayout.num_pe
        num_nodes_per_pe = config.addresslayout.num_nodes_per_pe

        self.apply_interface = [ApplyInterface(**config.addresslayout.get_params()) for _ in range(num_pe)]
        self.network_interface = [NetworkInterface(**config.addresslayout.get_params()) for _ in range(num_pe)]

        fifos = [[RecordFIFO(layout=Message(**config.addresslayout.get_params()).layout, depth=8) for i in range(num_pe)] for j in range(num_pe)]
        self.submodules.fifos = fifos
        self.submodules.arbiter = [Arbiter(config, fifos[sink]) for sink in range(num_pe)]

        self.comb += [self.arbiter[i].apply_interface.connect(self.apply_interface[i]) for i in range(num_pe)]

        # connect fifos across PEs
        for source in range(num_pe):
            array_dest_id = Array(fifo.din.dest_id for fifo in [fifos[sink][source] for sink in range(num_pe)])
            array_sender = Array(fifo.din.sender for fifo in [fifos[sink][source] for sink in range(num_pe)])
            array_payload = Array(fifo.din.payload for fifo in [fifos[sink][source] for sink in range(num_pe)])
            array_roundpar = Array(fifo.din.roundpar for fifo in [fifos[sink][source] for sink in range(num_pe)])
            array_barrier = Array(fifo.din.barrier for fifo in [fifos[sink][source] for sink in range(num_pe)])
            array_we = Array(fifo.we for fifo in [fifos[sink][source] for sink in range(num_pe)])
            array_writable = Array(fifo.writable for fifo in [fifos[sink][source] for sink in range(num_pe)])

            have_barrier = Signal()
            barrier_ack = Array(Signal() for _ in range(num_pe))
            barrier_done = Signal()

            self.comb += barrier_done.eq(reduce(and_, barrier_ack)), have_barrier.eq(self.network_interface[source].msg.barrier & self.network_interface[source].valid)

            self.sync += If(have_barrier & ~barrier_done,
                            [barrier_ack[i].eq(barrier_ack[i] | array_writable[i]) for i in range(num_pe)]
                         ).Else(
                            [barrier_ack[i].eq(0) for i in range(num_pe)]
                         )

            sink = Signal(config.addresslayout.peidsize)

            self.comb+= If(have_barrier,
                            [array_barrier[i].eq(1) for i in range(num_pe)],
                            [array_roundpar[i].eq(self.network_interface[source].msg.roundpar) for i in range(num_pe)],
                            [array_we[i].eq(~barrier_ack[i]) for i in range(num_pe)],
                            self.network_interface[source].ack.eq(barrier_done)
                        ).Else(
                            sink.eq(self.network_interface[source].dest_pe),
                            array_dest_id[sink].eq(self.network_interface[source].msg.dest_id),
                            array_sender[sink].eq(self.network_interface[source].msg.sender),
                            array_payload[sink].eq(self.network_interface[source].msg.payload),
                            array_roundpar[sink].eq(self.network_interface[source].msg.roundpar),
                            array_we[sink].eq(self.network_interface[source].valid),
                            self.network_interface[source].ack.eq(array_writable[sink])
                        )
