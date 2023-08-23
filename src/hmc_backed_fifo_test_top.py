from migen import *
from tbsupport import *
from migen.fhdl import verilog
import migen.build.xilinx.common
from migen.genlib.resetsync import AsyncResetSynchronizer
from migen.genlib.cdc import *

from util.pico import PicoPlatform

from hmc_backed_fifo import HMCBackedFIFO

class Top(Module):
    def __init__(self, pico):

        self.submodules.dut = HMCBackedFIFO(width=32, start_addr=0x1000, end_addr=0x11000, port=pico.getHMCPort(0))

        start = Signal()
        done = Signal()
        cycle_count = Signal(32)
        num_errors = Signal()

        num_tests = 2**20
        curr_test_in = Signal(32)
        curr_test_out = Signal(32)

        self.comb += [
            self.dut.din.eq(curr_test_in),
            self.dut.we.eq(start & curr_test_in < num_tests),
            self.dut.re.eq(start),
            done.eq(curr_test_out == num_tests)
        ]

        self.sync += [
            If(self.dut.writable & self.dut.we,
                curr_test_in.eq(curr_test_in + 1)
            ),
            If(self.dut.readable & self.dut.re,
                curr_test_out.eq(curr_test_out + 1),
                If(self.dut.dout != curr_test_out,
                    num_errors.eq(num_errors + 1)
                )
            )
        ]

        self.clock_domains.cd_sys = ClockDomain()
        sys_clk, _, sys_rst, _ = pico.getHMCClkEtc()
        self.comb += [ self.cd_sys.clk.eq(sys_clk), self.cd_sys.rst.eq(sys_rst) ]

        self.clock_domains.cd_pico = ClockDomain()
        bus_clk, bus_rst = pico.getBusClkRst()
        self.comb += [ self.cd_pico.clk.eq(bus_clk), self.cd_pico.rst.eq(bus_rst) ]

        start_pico = Signal()
        start_pico.attr.add("no_retiming")
        self.specials += [
            MultiReg(start_pico, start, odomain="sys")
        ]

        done_pico = Signal()
        done.attr.add("no_retiming")
        self.specials += [
            MultiReg(done, done_pico, odomain="pico")
        ]

        cycle_count_pico = Signal(len(cycle_count))
        self.submodules.cycle_count_transfer = BusSynchronizer(len(cycle_count), "sys", "pico")
        self.comb += [
            self.cycle_count_transfer.i.eq(cycle_count),
            cycle_count_pico.eq(self.cycle_count_transfer.o)
        ]

        num_errors_pico = Signal(len(num_errors))
        self.submodules.num_errors_transfer = BusSynchronizer(len(num_errors), "sys", "pico")
        self.comb += [
            self.num_errors_transfer.i.eq(num_errors),
            num_errors_pico.eq(self.num_errors_transfer.o)
        ]

        self.bus = pico.getBus()

        self.sync.pico += [
            If( self.bus.PicoRd & (self.bus.PicoAddr == 0x10000),
                self.bus.PicoDataOut.eq(cycle_count_pico)
            ),
            If( self.bus.PicoRd & (self.bus.PicoAddr == 0x10004),
                self.bus.PicoDataOut.eq(done_pico)
            ),
            If( self.bus.PicoRd & (self.bus.PicoAddr == 0x10008),
                self.bus.PicoDataOut.eq(num_errors_pico)
            ),
            If( self.bus.PicoWr & (self.bus.PicoAddr == 0x20000),
                start_pico.eq(1)
            )
        ]

def main():
    pico = PicoPlatform(1, bus_width=32, stream_width=128)

    m = Top(pico)

    so = dict(migen.build.xilinx.common.xilinx_special_overrides)
    verilog.convert(m,
                    name="echo",
                    ios=pico.get_ios(),
                    special_overrides=so,
                    create_clock_domains=False
                    ).write("top.v")

if __name__ == '__main__':
    main()
