from migen import *

from migen.genlib.roundrobin import *

from functools import reduce
from operator import and_

from recordfifo import RecordFIFOBuffered
from core_interfaces import _msg_layout, ApplyInterface, NetworkInterface
from core_arbiter import Arbiter

class Network(Module):
    def __init__(self, config):
        num_pe = config.addresslayout.num_pe
        num_nodes_per_pe = config.addresslayout.num_nodes_per_pe

        self.apply_interface = [ApplyInterface(**config.addresslayout.get_params()) for _ in range(num_pe)]
        self.network_interface = [NetworkInterface(**config.addresslayout.get_params()) for _ in range(num_pe)]

        #TODO: change to SyncFIFOBuffered
        fifos = [[RecordFIFOBuffered(layout=set_layout_parameters(_msg_layout, **config.addresslayout.get_params()),
                             depth=8#,
                             #delay=(0 if i%config.addresslayout.pe_groups == j%config.addresslayout.pe_groups else config.addresslayout.inter_pe_delay)
                             ) for i in range(num_pe)] for j in range(num_pe)]
        self.submodules.fifos = fifos
        self.submodules.arbiter = [Arbiter(sink, config) for sink in range(num_pe)]

        for sink in range(num_pe):
            self.submodules.roundrobin = RoundRobin(num_pe, switch_policy=SP_CE)

            # arrays for choosing incoming fifo to use
            array_data = Array(fifo.dout.raw_bits() for fifo in fifos[sink])
            array_re = Array(fifo.re for fifo in fifos[sink])
            array_readable = Array(fifo.readable for fifo in fifos[sink])
            array_barrier = Array(fifo.dout.barrier for fifo in fifos[sink])
            array_round = Array(fifo.dout.roundpar for fifo in fifos[sink])

            roundpar = Signal(config.addresslayout.channel_bits)

            array_apply_interface_in_valid = Array(x.valid for x in self.arbiter[sink].apply_interface_in)
            array_apply_interface_in_ack = Array(x.ack for x in self.arbiter[sink].apply_interface_in)

            msg_layout = set_layout_parameters(_msg_layout, **config.addresslayout.get_params())
            round_start = 0
            for field, length, _ in msg_layout:
                if field == "roundpar":
                    round_length = length
                    break
                round_start += length

            self.comb += [
                roundpar.eq(array_data[self.roundrobin.grant][round_start:round_start+round_length]),
                [x.msg.raw_bits().eq(array_data[self.roundrobin.grant]) for x in self.arbiter[sink].apply_interface_in],
                array_apply_interface_in_valid[roundpar].eq(array_readable[self.roundrobin.grant]),
                array_re[self.roundrobin.grant].eq(array_apply_interface_in_ack[roundpar]),
                [self.roundrobin.request[i].eq(array_readable[i]) for i in range(num_pe)],
                self.roundrobin.ce.eq(array_apply_interface_in_ack[roundpar])
            ]

        self.comb += [ self.arbiter[i].apply_interface_out.connect(self.apply_interface[i]) for i in range(num_pe) ]



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

            num_msgs_since_last_barrier = Array(Signal(config.addresslayout.nodeidsize) for _ in range(num_pe))

            self.sync += [
                If(barrier_done,
                    [num_msgs_since_last_barrier[i].eq(0) for i in range(num_pe)]
                ).Elif(~have_barrier & self.network_interface[source].valid & self.network_interface[source].ack,
                    num_msgs_since_last_barrier[sink].eq(num_msgs_since_last_barrier[sink]+1)
                )
            ]

            self.comb+= If(have_barrier,
                            [array_barrier[i].eq(1) for i in range(num_pe)],
                            [array_roundpar[i].eq(self.network_interface[source].msg.roundpar) for i in range(num_pe)],
                            [array_we[i].eq(~barrier_ack[i]) for i in range(num_pe)],
                            [array_sender[i].eq(self.network_interface[source].msg.sender) for i in range(num_pe)],
                            [array_dest_id[i].eq(num_msgs_since_last_barrier[i]) for i in range(num_pe)],
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