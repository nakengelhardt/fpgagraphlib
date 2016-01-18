from migen import *
from migen.genlib.record import *
from migen.genlib.fifo import _FIFOInterface, _inc, SyncFIFOBuffered

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

class InitFIFO(Module, _FIFOInterface):
    """Synchronous FIFO (first in, first out)

    Read and write interfaces are accessed from the same clock domain.
    If different clock domains are needed, use :class:`AsyncFIFO`.

    {interface}
    level : out
        Number of unread entries.
    replace : in
        Replaces the last entry written into the FIFO with `din`. Does nothing
        if that entry has already been read (i.e. the FIFO is empty).
        Assert in conjunction with `we`.
    """
    __doc__ = __doc__.format(interface=_FIFOInterface.__doc__)

    def __init__(self, width, depth, fwft=True, init=None):
        _FIFOInterface.__init__(self, width, depth)

        if init:
            startlevel = len(init)
        else:
            startlevel = 0

        self.level = Signal(max=depth+1, reset=startlevel)
        self.replace = Signal()

        ###

        produce = Signal(max=depth, reset=startlevel)
        consume = Signal(max=depth)
        storage = Memory(self.width, depth, init=init)
        self.specials += storage

        wrport = storage.get_port(write_capable=True)
        self.specials += wrport
        self.comb += [
            If(self.replace,
                wrport.adr.eq(produce-1)
            ).Else(
                wrport.adr.eq(produce)
            ),
            wrport.dat_w.eq(self.din),
            wrport.we.eq(self.we & (self.writable | self.replace))
        ]
        self.sync += If(self.we & self.writable & ~self.replace,
            _inc(produce, depth))

        do_read = Signal()
        self.comb += do_read.eq(self.readable & self.re)

        rdport = storage.get_port(async_read=fwft, has_re=not fwft)
        self.specials += rdport
        self.comb += [
            rdport.adr.eq(consume),
            self.dout.eq(rdport.dat_r)
        ]
        if not fwft:
            self.comb += rdport.re.eq(do_read)
        self.sync += If(do_read, _inc(consume, depth))

        self.sync += \
            If(self.we & self.writable & ~self.replace,
                If(~do_read, self.level.eq(self.level + 1))
            ).Elif(do_read,
                self.level.eq(self.level - 1)
            )
        self.comb += [
            self.writable.eq(self.level != depth),
            self.readable.eq(self.level != 0)
        ]

class RecordFIFO(Module):
    def __init__(self, layout, depth, init=None, delay=0):
        self.we = Signal()
        self.writable = Signal()  # not full
        self.re = Signal()
        self.readable = Signal()  # not empty

        self.din = Record(layout)
        self.dout = Record(layout)
        self.width = len(self.din.raw_bits())

        self.submodules.fifo = InitFIFO(self.width, depth, init=init)

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

class RecordFIFOBuffered(Module):
    def __init__(self, layout, depth):
        self.we = Signal()
        self.writable = Signal()  # not full
        self.re = Signal()
        self.readable = Signal()  # not empty

        self.din = Record(layout)
        self.dout = Record(layout)
        self.width = len(self.din.raw_bits())

        self.submodules.fifo = SyncFIFOBuffered(self.width, depth)

        self.comb += [
            self.fifo.din.eq(self.din.raw_bits()),
            self.writable.eq(self.fifo.writable),
            self.fifo.we.eq(self.we),
            self.dout.raw_bits().eq(self.fifo.dout),
            self.readable.eq(self.fifo.readable),
            self.fifo.re.eq(self.re)
        ]