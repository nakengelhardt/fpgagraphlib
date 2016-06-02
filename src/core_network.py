from migen import *

from functools import reduce
from operator import and_

from recordfifo import RecordFIFOBuffered
from core_interfaces import Message, ApplyInterface, NetworkInterface
from core_arbiter import Arbiter

class Network(Module):
    def __init__(self, config):
        num_pe = config.addresslayout.num_pe
        num_nodes_per_pe = config.addresslayout.num_nodes_per_pe

        self.apply_interface = [ApplyInterface(**config.addresslayout.get_params()) for _ in range(num_pe)]
        self.network_interface = [NetworkInterface(**config.addresslayout.get_params()) for _ in range(num_pe)]

        fifos = [[RecordFIFOBuffered(layout=Message(**config.addresslayout.get_params()).layout,
                             depth=8#,
                             #delay=(0 if i%config.addresslayout.pe_groups == j%config.addresslayout.pe_groups else config.addresslayout.inter_pe_delay)
                             ) for i in range(num_pe)] for j in range(num_pe)]
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
