from migen import *
from migen.genlib.record import *
from migen.genlib.fifo import _FIFOInterface, _inc, SyncFIFO, SyncFIFOBuffered

from tbsupport import *

class _Compacter(Module):
    """Receive up to `num_in` data elements of width `datawidth` in random positions
    Output them consecutively and give count
    """
    def __init__(self, elementwidth, nelements):
        self.data_in = Signal(nelements*elementwidth)
        self.valid_in = Signal(nelements)
        self.ack_in = Signal()

        self.data_out = Signal(nelements*elementwidth)
        self.num_out = Signal(max=nelements+1)
        self.valid_out = Signal()
        self.ack_out = Signal()

        self.sync += Case(self.valid_in,
        {i: [If(self.ack_out,
            self.data_out.eq(Cat([self.data_in[j*elementwidth:(j+1)*elementwidth] for j in range(nelements) if (1<<j)&i])),
            self.num_out.eq(popcount(i)),
            self.valid_out.eq(self.valid_in != 0)
            )] for i in range(2**nelements)})

        self.comb += [
            self.ack_in.eq(self.ack_out)
        ]

class _Slicer(Module):
    def __init__(self, elementwidth, nelements):
        self.data_in = Signal(nelements * elementwidth)
        self.num_in = Signal(max=nelements + 1)
        self.valid_in = Signal()
        self.ack_in = Signal()

        self.data_out = Signal(nelements * elementwidth)
        self.num_out = Signal(max=nelements + 1)
        self.valid_out = Signal()
        self.ack_out = Signal()
        self.flush = Signal()

        data_in_array = Array(self.data_in[i*elementwidth:(i+1)*elementwidth] for i in range(nelements))
        buf = Array(Signal(elementwidth) for _ in range(2 * nelements - 1))
        num_full = Signal(max=2 * nelements)
        num_remain = Signal(max=2 * nelements)
        num_wr = Signal(max=nelements + 1)
        do_wr = Signal()
        next_buf = Array(Signal(elementwidth) for _ in range(2 * nelements - 1))

        self.comb += [
            self.ack_in.eq(self.ack_out | ~do_wr),
            do_wr.eq(num_full >= nelements),
            If(do_wr & self.ack_out,
                num_wr.eq(nelements)
            ).Elif(self.flush & self.ack_out,
                num_wr.eq(num_full)
            ).Else(
                num_wr.eq(0)
            ),
            If(do_wr,
                self.num_out.eq(nelements),
                self.valid_out.eq(1)
            ).Else(
                self.num_out.eq(num_full),
                self.valid_out.eq(self.flush & (self.num_out > 0))
            ),
            num_remain.eq(num_full - num_wr),
            self.data_out.eq(Cat(buf[i] for i in range(nelements)))
        ]

        self.sync += [
            If(self.valid_in & self.ack_in,
                num_full.eq(num_remain + self.num_in),
            ).Else(
                num_full.eq(num_remain)
            ),
            [If(i < num_remain,
                buf[i].eq(buf[i+num_wr])
            ).Elif((i - num_remain) < self.num_in,
                buf[i].eq(data_in_array[i - num_remain])
            ) for i in range(2 * nelements - 1)]
        ]

class _DownConverter(Module):
    def __init__(self, elementwidth, nelements_from, nelements_to):
        ratio = nelements_from//nelements_to
        assert nelements_to*ratio == nelements_from

        self.data_in = Signal(nelements_from * elementwidth)
        self.num_in = Signal(max=nelements_from + 1)
        self.valid_in = Signal()
        self.ack_in = Signal()

        self.data_out = Signal(nelements_to * elementwidth)
        self.num_out = Signal(max=nelements_to + 1)
        self.valid_out = Signal()
        self.ack_out = Signal()

        # # #

        # control path
        mux = Signal(max=nelements_from+1)
        last = Signal()
        self.comb += [
            last.eq(mux + nelements_to >= self.num_in),
            self.valid_out.eq(self.valid_in),
            self.ack_in.eq(last & self.ack_out),
            If(last,
                self.num_out.eq(self.num_in - mux)
            ).Else(
                self.num_out.eq(nelements_to)
            )
        ]
        self.sync += [
            If(self.valid_out & self.ack_out,
                If(last,
                    mux.eq(0)
                ).Else(
                    mux.eq(mux + nelements_to)
                )
            )
        ]

        # data path
        cases = {}
        for i in range(ratio):
            cases[i*nelements_to] = self.data_out.eq(self.data_in[i*nelements_to*elementwidth:(i+1)*nelements_to*elementwidth])
        self.comb += Case(mux, cases).makedefault()

class MultiEntryFIFO(Module):
    def __init__(self, elementwidth, num_in, num_out, depth, name=None):

        self.din = Signal(num_in*elementwidth, name_override=name+"_din" if name else None)
        self.nin = Signal(max=num_in+1, name_override=name+"_nin" if name else None)
        self.writable = Signal(name_override=name+"_writable" if name else None)
        self.we = Signal(name_override=name+"_we" if name else None)

        self.dout = Signal(num_out*elementwidth, name_override=name+"_dout" if name else None)
        self.readable = Signal(num_out, name_override=name+"_readable" if name else None)
        self.re = Signal(name_override=name+"_re" if name else None)

        self.submodules.slice = _Slicer(elementwidth=elementwidth, nelements=num_in)

        self.comb += [
            self.slice.data_in.eq(self.din),
            self.slice.num_in.eq(self.nin),
            self.slice.valid_in.eq(self.we),
            self.writable.eq(self.slice.ack_in)
        ]

        storage = SyncFIFO(width=elementwidth*num_in+len(self.slice.num_out), depth=depth)
        self.submodules += storage

        self.comb += [
            storage.din.eq(Cat(self.slice.data_out, self.slice.num_out)),
            storage.we.eq(self.slice.valid_out),
            self.slice.ack_out.eq(storage.writable),
            self.slice.flush.eq(~storage.readable)
        ]

        self.submodules.downconvert = _DownConverter(elementwidth=elementwidth, nelements_from=num_in, nelements_to=num_out)

        self.comb += [
            self.downconvert.data_in.eq(storage.dout[:elementwidth*num_in]),
            self.downconvert.num_in.eq(storage.dout[elementwidth*num_in:]),
            self.downconvert.valid_in.eq(storage.readable),
            storage.re.eq(self.downconvert.ack_in),

            self.dout.eq(self.downconvert.data_out),
            If(self.downconvert.valid_out,
                self.readable.eq(self.downconvert.num_out)
            ).Else(
                self.readable.eq(0)
            ),
            self.downconvert.ack_out.eq(self.re)
        ]

class SortEntryFIFO(Module):
    def __init__(self, elementwidth, num_in, num_out, depth, name=None):
        self.din = Signal(num_in*elementwidth, name_override=name+"_din" if name else None)
        self.writable = Signal(name_override=name+"_writable" if name else None)
        self.we = Signal(num_in, name_override=name+"_we" if name else None)

        self.submodules.compact = _Compacter(elementwidth=elementwidth, nelements=num_in)
        self.submodules.multientryfifo = MultiEntryFIFO(elementwidth=elementwidth, num_in=num_in, num_out=num_out, depth=depth, name=name)

        self.dout = self.multientryfifo.dout
        self.readable = self.multientryfifo.readable
        self.re = self.multientryfifo.re

        self.comb += [
            self.compact.data_in.eq(self.din),
            self.compact.valid_in.eq(self.we),
            self.writable.eq(self.compact.ack_in),

            self.multientryfifo.din.eq(self.compact.data_out),
            self.multientryfifo.nin.eq(self.compact.num_out),
            self.multientryfifo.we.eq(self.compact.valid_out),
            self.compact.ack_out.eq(self.multientryfifo.writable)
        ]
