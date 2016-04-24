from migen import *
from migen.genlib.record import *
from migen.fhdl import verilog
import migen.build.xilinx.common
from migen.genlib.fifo import SyncFIFO, AsyncFIFO
from migen.genlib.cdc import *

from pico import PicoPlatform

from core_neighbors_hmc import Neighbors

from types import SimpleNamespace

class Top(Module):
    def __init__(self, platform):
        self.clock_domains.cd_pico = ClockDomain()
        bus_clk, bus_rst = platform.getBusClkRst()
        self.comb += [ self.cd_pico.clk.eq(bus_clk), self.cd_pico.rst.eq(bus_rst) ]

        self.clock_domains.cd_sys = ClockDomain()
        sys_clk, _, sys_rst, _ = platform.getHMCClkEtc()
        self.comb += [ self.cd_sys.clk.eq(sys_clk), self.cd_sys.rst.eq(sys_rst) ]

        self.clock_domains.cd_pcie = ClockDomain()
        clk, rst = platform.getStreamClkRst()
        self.comb += [ self.cd_pcie.clk.eq(clk), self.cd_pcie.rst.eq(rst) ]

        self.bus = platform.getBus()
        addr = Signal(30)

        control_regs = [Signal(32) for _ in range(4)]
        base_addr = 0x10000
        start_addr = 0x20000

        status_regs = [Signal(32) for _ in range(8)]

        self.sync.pico += [
            self.bus.PicoDataOut.eq(0),
            [If( self.bus.PicoRd & (self.bus.PicoAddr == base_addr + i*4),
                self.bus.PicoDataOut.eq(csr)
            ) for i, csr in enumerate(control_regs + status_regs)],
            [If( self.bus.PicoWr & (self.bus.PicoAddr == base_addr + i*4),
                csr.eq(self.bus.PicoDataIn)
            ) for i, csr in enumerate(control_regs)]
        ]

        self.submodules.start = PulseSynchronizer("pico", "sys")
        self.comb += [
            If( self.bus.PicoWr & (self.bus.PicoAddr == start_addr),
                self.start.i.eq(1)
            )
        ]


        control_regs_sys = [Signal(32) for _ in control_regs]

        self.submodules.control_regs_transfer = BusSynchronizer(len(control_regs)*32, "pico", "sys")
        self.comb += [
            self.control_regs_transfer.i.eq(Cat(*control_regs)),
            Cat(*control_regs_sys).eq(self.control_regs_transfer.o)
        ]

        status_regs_sys = [Signal(32) for _ in status_regs]

        self.submodules.status_regs_transfer = BusSynchronizer(len(status_regs_sys)*32, "sys", "pico")
        self.comb += [
            self.status_regs_transfer.i.eq(Cat(*status_regs_sys)),
            Cat(*status_regs).eq(self.status_regs_transfer.o)
        ]

        # request memory lookup
        addresslayout = SimpleNamespace(nodeidsize=32, edgeidsize=32, payloadsize=32)
        config = SimpleNamespace(platform=platform, addresslayout=addresslayout)
        self.submodules.neighbors = Neighbors(config, 0, hmc_port=platform.getHMCPort(0))

        valid = Signal()
        self.sync += [
            If(self.start.o,
                valid.eq(1)
            ).Elif(self.neighbors.ack,
                valid.eq(0)
            )
        ]

        self.comb += [
            self.neighbors.start_idx.eq(control_regs_sys[0]),
            self.neighbors.num_neighbors.eq(control_regs_sys[1]),
            self.neighbors.valid.eq(valid),
            self.neighbors.barrier_in.eq(0),
            self.neighbors.message_in.eq(control_regs_sys[2]),
            self.neighbors.sender_in.eq(control_regs_sys[3]),
            self.neighbors.round_in.eq(0)
        ]

        self.comb += [
            status_regs_sys[0].eq(self.neighbors.num_requests_accepted),
            status_regs_sys[1].eq(self.neighbors.num_hmc_commands_issued),
            status_regs_sys[2].eq(self.neighbors.num_hmc_commands_retired),
            status_regs_sys[3].eq(self.neighbors.num_hmc_responses)
        ]

        self.sync += [
            If(valid, status_regs_sys[4].eq(1)),
            If(self.neighbors.valid & self.neighbors.ack, status_regs_sys[5].eq(status_regs_sys[5] + 1)),
            If(self.neighbors.neighbor_valid & self.neighbors.neighbor_ack, status_regs_sys[6].eq(status_regs_sys[6] + 1)),
            If(self.neighbors.valid & self.neighbors.ack, status_regs_sys[7].eq(self.neighbors.num_neighbors)),
        ]

        fifo_depth = 256
        self.submodules.read_fifo = ClockDomainsRenamer({"write": "sys", "read": "pcie"})(AsyncFIFO(128, fifo_depth))

        self.comb += [
            self.read_fifo.din.eq(Cat(self.neighbors.neighbor, self.neighbors.num_neighbors_out, self.neighbors.message_out, self.neighbors.sender_out)),
            self.read_fifo.we.eq(self.neighbors.neighbor_valid),
            self.neighbors.neighbor_ack.eq(self.read_fifo.writable)
        ]

        # send data back to host over PCIe
        rx, tx = platform.getStreamPair()

        self.comb += [
            tx.data.eq( self.read_fifo.dout ),
            tx.valid.eq( self.read_fifo.readable ),
            self.read_fifo.re.eq( tx.rdy )
        ]

def export(filename='echo.v'):

    platform = PicoPlatform(bus_width=32, stream_width=128)

    m = Top(platform)

    so = dict(migen.build.xilinx.common.xilinx_special_overrides)
    verilog.convert(m,
                    name="echo",
                    ios=platform.get_ios(),
                    special_overrides=so,
                    create_clock_domains=False
                    ).write(filename)

if __name__ == "__main__":
    export()
