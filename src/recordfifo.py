from migen import *
from migen.genlib.record import *
from migen.genlib.fifo import _FIFOInterface, _inc, SyncFIFO, SyncFIFOBuffered


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

        self.almost_full = Signal()
        ###

        produce = Signal(max=depth, reset=startlevel)
        consume = Signal(max=depth)
        storage = Memory(self.width, depth, init=init)
        self.specials += storage

        wrport = storage.get_port(write_capable=True, mode=READ_FIRST)
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

        rdport = storage.get_port(async_read=fwft, has_re=not fwft, mode=READ_FIRST)
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
            self.readable.eq(self.level != 0),
            self.almost_full.eq(self.level >= depth - 1)
        ]

class RecordFIFO(Module):
    def __init__(self, layout, depth, init=None, name=None):
        self.din = Record(layout, name= (name + "_din") if name else None)
        self.dout = Record(layout, name= (name + "_dout") if name else None)
        self.width = len(self.din.raw_bits())

        self.submodules.fifo = InitFIFO(self.width, depth, init=init)

        self.we = self.fifo.we
        self.writable = self.fifo.writable
        self.re = self.fifo.re
        self.readable = self.fifo.readable
        self.almost_full = self.fifo.almost_full
        
        self.comb += [
            self.fifo.din.eq(self.din.raw_bits()),
            self.dout.raw_bits().eq(self.fifo.dout)
        ]

class RecordFIFOBuffered(Module):
    def __init__(self, layout, depth, name=None):
        self.we = Signal()
        self.writable = Signal()  # not full
        self.re = Signal()
        self.readable = Signal()  # not empty

        self.din = Record(layout, name= (name + "_din") if name else None)
        self.dout = Record(layout, name= (name + "_dout") if name else None)
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

class InterfaceFIFO(Module):
    def __init__(self, layout, depth, name=None):

        self.din = Record(layout, name= (name + "_din") if name else None)
        self.dout = Record(layout, name= (name + "_dout") if name else None)

        datalayout = [field for field in layout if (field[0] != "valid") and (field[0] != "ack")]

        self.width = layout_len(datalayout)

        self.submodules.fifo = RecordFIFO(datalayout, depth)

        self.comb += [
            self.din.connect(self.fifo.din, omit={"valid", "ack"}),
            self.din.ack.eq(self.fifo.writable),
            self.fifo.we.eq(self.din.valid),
            self.fifo.dout.connect(self.dout, omit={"valid", "ack"}),
            self.dout.valid.eq(self.fifo.readable),
            self.fifo.re.eq(self.dout.ack)
        ]

class InterfaceFIFOBuffered(Module):
    def __init__(self, layout, depth, name=None):

        self.din = Record(layout, name= (name + "_din") if name else None)
        self.dout = Record(layout, name= (name + "_dout") if name else None)

        datalayout = [field for field in layout if (field != "valid") and (field != "ack")]

        self.width = layout_len(datalayout)

        self.submodules.fifo = RecordFIFOBuffered(datalayout, depth)

        self.comb += [
            self.din.connect(self.fifo.din, omit={"valid", "ack"}),
            self.din.ack.eq(self.fifo.writable),
            self.fifo.we.eq(self.din.valid),
            self.fifo.dout.connect(self.dout),
            self.dout.valid.eq(self.fifo.readable),
            self.fifo.re.eq(self.dout.ack)
        ]
