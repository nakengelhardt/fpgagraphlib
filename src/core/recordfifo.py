from migen import *
from migen.genlib.record import *
from migen.genlib.fifo import SyncFIFO

@CEInserter()
class Delay(Module):
    def __init__(self, s_in, ncycles):
        self.s_out = Signal(len(s_in))
        if ncycles > 0:
            s_delay = [Signal(len(s_in)) for _ in range(ncycles)]
            self.sync += [
                s_delay[0].eq(s_in),
                [s_delay[i].eq(s_delay[i-1]) for i in range(1, ncycles)]
            ]
            self.comb += self.s_out.eq(s_delay[-1])
        else:
            self.comb += self.s_out.eq(s_in)

class RecordFIFO(Module):
    def __init__(self, layout, depth, init=None, delay=0):
        self.we = Signal()
        self.writable = Signal()  # not full
        self.re = Signal()
        self.readable = Signal()  # not empty

        self.din = Record(layout)
        self.dout = Record(layout)
        self.width = len(self.din.raw_bits())

        self.submodules.fifo = SyncFIFO(self.width, depth, init=init)

        if delay > 0:
            fifolayout = [
                ("din", len(self.din.raw_bits())),
                ("we", 1)
            ]
            s_in = Record(fifolayout)
            s_out = Record(fifolayout)
            self.submodules.delay = Delay(s_in.raw_bits(), delay)
            self.comb += [
                s_out.raw_bits().eq(self.delay.s_out),
                self.delay.ce.eq(self.fifo.writable),
                s_in.din.eq(self.din.raw_bits()),
                s_in.we.eq(self.we),
                self.fifo.din.eq(s_out.din),
                self.fifo.we.eq(s_out.we),
                self.writable.eq(self.fifo.writable),
                self.dout.raw_bits().eq(self.fifo.dout),
                self.readable.eq(self.fifo.readable),
                self.fifo.re.eq(self.re)
            ]

        else:
            self.comb += [
                self.fifo.din.eq(self.din.raw_bits()),
                self.writable.eq(self.fifo.writable),
                self.fifo.we.eq(self.we),
                self.dout.raw_bits().eq(self.fifo.dout),
                self.readable.eq(self.fifo.readable),
                self.fifo.re.eq(self.re)
            ]