from migen import *

from core_interfaces import NetworkInterface
from util.recordfifo import *

class BarrierDistributor(Module):
    def __init__(self, config):
        self.network_interface_in = NetworkInterface(name="barrierdistributor_in", **config.addresslayout.get_params())
        self.network_interface_out = NetworkInterface(name="barrierdistributor_out", **config.addresslayout.get_params())

        self.submodules.fifo = InterfaceFIFO(layout=self.network_interface_in.layout, depth=8)

        self.comb += [
            self.network_interface_in.connect(self.fifo.din)
        ]

        self.total_num_messages = Signal(32)
        self.sync += [
            If(self.network_interface_out.valid & self.network_interface_out.ack & ~self.network_interface_out.msg.barrier,
                self.total_num_messages.eq(self.total_num_messages + 1)
            )
        ]

        num_pe = config.addresslayout.num_pe

        have_barrier = Signal()
        curr_barrier = Signal(config.addresslayout.peidsize)
        barrier_done = Signal()
        sink = Signal(config.addresslayout.peidsize)
        num_msgs_since_last_barrier = Array(Signal(config.addresslayout.nodeidsize) for _ in range(num_pe))
        halt = Signal()

        self.comb += [
            have_barrier.eq(self.fifo.dout.msg.barrier & self.fifo.dout.valid),
            barrier_done.eq(curr_barrier == (num_pe - 1))
        ]

        self.sync += [
            If(have_barrier & self.network_interface_out.ack,
                num_msgs_since_last_barrier[curr_barrier].eq(0),
                If(~barrier_done,
                    curr_barrier.eq(curr_barrier + 1)
                ).Else(
                    curr_barrier.eq(0),
                    halt.eq(1)
                )
            )
        ]

        self.sync += [
            If(~have_barrier & self.fifo.dout.valid & self.fifo.dout.ack,
                num_msgs_since_last_barrier[sink].eq(num_msgs_since_last_barrier[sink] + 1),
                halt.eq(0)
            )
        ]

        self.comb += [
            If(have_barrier,
                sink.eq(curr_barrier),
                self.network_interface_out.dest_pe.eq(curr_barrier),
                self.network_interface_out.msg.dest_id.eq(num_msgs_since_last_barrier[sink]),
                self.network_interface_out.msg.halt.eq(halt),
                self.fifo.dout.ack.eq(barrier_done & self.network_interface_out.ack)
            ).Else(
                sink.eq(self.fifo.dout.dest_pe),
                self.network_interface_out.dest_pe.eq(self.fifo.dout.dest_pe),
                self.network_interface_out.msg.dest_id.eq(self.fifo.dout.msg.dest_id),
                self.network_interface_out.msg.halt.eq(0),
                self.fifo.dout.ack.eq(self.network_interface_out.ack)
            ),
            self.fifo.dout.connect(self.network_interface_out, omit=["ack", "dest_id", "dest_pe", "halt"])
        ]
