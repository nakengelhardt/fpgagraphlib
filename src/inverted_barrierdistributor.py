from migen import *

from core_interfaces import *
from util.recordfifo import *

class BarrierDistributorApply(Module):
    def __init__(self, config):
        self.apply_interface_in = ApplyInterface(name="barrierdistributor_in", **config.addresslayout.get_params())
        self.apply_interface_out = ApplyInterface(name="barrierdistributor_out", **config.addresslayout.get_params())

        self.submodules.fifo = InterfaceFIFO(layout=self.apply_interface_in.layout, depth=8)

        self.comb += [
            self.apply_interface_in.connect(self.fifo.din)
        ]

        self.total_num_updates = Signal(32)
        self.sync += [
            If(self.apply_interface_out.valid & self.apply_interface_out.ack & ~self.apply_interface_out.msg.barrier,
                self.total_num_updates.eq(self.total_num_updates + 1)
            )
        ]

        num_pe = config.addresslayout.num_pe

        have_barrier = Signal()
        num_msgs_since_last_barrier = Signal(config.addresslayout.nodeidsize)
        halt = Signal(reset=1)

        self.sync += [
            If(self.fifo.dout.valid & self.fifo.dout.ack,
                If(self.fifo.dout.msg.barrier,
                    num_msgs_since_last_barrier.eq(0),
                    halt.eq(1)
                ).Else(
                    num_msgs_since_last_barrier.eq(num_msgs_since_last_barrier + 1),
                    halt.eq(0)
                )
            )
        ]

        self.comb += [
            self.fifo.dout.connect(self.apply_interface_out, omit=["halt", "dest_id"]),
            self.apply_interface_out.msg.dest_id.eq(num_msgs_since_last_barrier),
            self.apply_interface_out.msg.halt.eq(halt)
        ]
