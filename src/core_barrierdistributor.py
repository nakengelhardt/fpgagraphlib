from migen import *

from core_interfaces import NetworkInterface

class BarrierDistributor(Module):
    def __init__(self, config):
        self.network_interface_in = NetworkInterface(**config.addresslayout.get_params())
        self.network_interface_out = NetworkInterface(**config.addresslayout.get_params())

        num_pe = config.addresslayout.num_pe

        have_barrier = Signal()
        curr_barrier = Signal(config.addresslayout.peidsize)
        barrier_done = Signal()
        sink = Signal(config.addresslayout.peidsize)
        num_msgs_since_last_barrier = Array(Signal(config.addresslayout.nodeidsize) for _ in range(num_pe))

        self.comb += [
            have_barrier.eq(self.network_interface_in.msg.barrier & self.network_interface_in.valid),
            barrier_done.eq(curr_barrier == (num_pe - 1))
        ]

        self.sync += [
            If(have_barrier & self.network_interface_out.ack,
                num_msgs_since_last_barrier[curr_barrier].eq(0),
                If(~barrier_done,
                    curr_barrier.eq(curr_barrier + 1)
                ).Else(
                    curr_barrier.eq(0)
                )
            )
        ]

        self.sync += [
            If(~have_barrier & self.network_interface_in.valid & self.network_interface_in.ack,
                num_msgs_since_last_barrier[sink].eq(num_msgs_since_last_barrier[sink]+1)
            )
        ]

        self.comb += [
            If(have_barrier,
                sink.eq(curr_barrier),
                self.network_interface_out.dest_pe.eq(curr_barrier),
                self.network_interface_out.msg.dest_id.eq(num_msgs_since_last_barrier[sink]),
                self.network_interface_in.ack.eq(barrier_done & self.network_interface_out.ack)
            ).Else(
                sink.eq(self.network_interface_in.dest_pe),
                self.network_interface_out.dest_pe.eq(self.network_interface_in.dest_pe),
                self.network_interface_out.msg.dest_id.eq(self.network_interface_in.msg.dest_id),
                self.network_interface_in.ack.eq(self.network_interface_out.ack)
            ),
            self.network_interface_in.connect(self.network_interface_out, leave_out=["ack", "dest_id", "dest_pe"])
        ]
