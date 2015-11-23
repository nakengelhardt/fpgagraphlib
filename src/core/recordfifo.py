from migen import *
from migen.genlib.fifo import SyncFIFO

class RecordFIFO(Module):
    def __init__(self, layout, depth, init=None):
        self.we = Signal()
        self.writable = Signal()  # not full
        self.re = Signal()
        self.readable = Signal()  # not empty

        self.din = Record(layout)
        self.dout = Record(layout)
        self.width = len(self.din.raw_bits())

        self.submodules.fifo = SyncFIFO(self.width, depth, init=init)

        self.comb += [
            self.fifo.we.eq(self.we),
            self.writable.eq(self.fifo.writable),
            self.fifo.re.eq(self.re),
            self.readable.eq(self.fifo.readable),
            self.fifo.din.eq(self.din.raw_bits()),
            self.dout.raw_bits().eq(self.fifo.dout)
        ]