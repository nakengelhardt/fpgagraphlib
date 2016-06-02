from migen import *
from migen.genlib.coding import PriorityEncoder

from pdiv import Divider

@CEInserter()
class FloatIntDivider(Module):
    """Divides a 32 bit floating point number by an integer. 50 cycles latency."""
    def __init__(self):
        self.latency = 50
        self.dividend_i = Signal(32)
        self.divisor_i = Signal(32)
        self.valid_i = Signal()
        self.quotient_o = Signal(32)
        self.valid_o = Signal()

        ###

        dividend_sign = Signal()
        dividend_expn = Signal(8)
        dividend_mant = Signal(24)

        self.comb += [
            dividend_sign.eq(self.dividend_i[31]),
            dividend_expn.eq(self.dividend_i[23:31]),
            dividend_mant.eq(Cat(self.dividend_i[0:23], 1))
        ]

        # divide mantissa, add 24 bits of precision to be sure we have at least 24 left over

        w = 48

        self.submodules.div = Divider(w)

        self.comb += [
            self.div.dividend_i[:-24].eq(0),
            self.div.dividend_i[-24:].eq(dividend_mant),
            self.div.divisor_i.eq(self.divisor_i),
            self.div.valid_i.eq(self.valid_i)
        ]

        # keep exponent and sign for the duration of division (49 cycles...)

        expn = [Signal(8) for _ in range(w+1)]
        sign = [Signal() for _ in range(w+1)]

        self.sync += [
            expn[0].eq(dividend_expn),
            sign[0].eq(dividend_sign)
        ]

        self.sync += [ expn[i+1].eq(expn[i]) for i in range(w) ]

        self.sync += [ sign[i+1].eq(sign[i]) for i in range(w) ]

        # shift mantissa and subtract shift from exponent

        pe = PriorityEncoder(w)
        self.submodules += pe

        self.comb += [
            pe.i.eq(self.div.quotient_o[::-1])
        ]

        quotient_o_sign = Signal()
        quotient_o_expn = Signal(8)
        quotient_o_mant = Signal(48)

        self.sync += [
            quotient_o_sign.eq(sign[-1]),
            If(expn[-1] != 0,
                quotient_o_expn.eq(expn[-1] - pe.o),
                quotient_o_mant.eq(self.div.quotient_o << pe.o)
            ).Else(
                quotient_o_expn.eq(0),
                quotient_o_mant.eq(self.div.quotient_o)
            ),
            self.valid_o.eq(self.div.valid_o)
        ]

        self.comb += [
            self.quotient_o[31].eq(quotient_o_sign),
            self.quotient_o[23:31].eq(quotient_o_expn),
            self.quotient_o[0:23].eq(quotient_o_mant[-24:-1])
        ]

if __name__ == "__main__":
    from migen.fhdl import verilog

    m = FloatIntDivider()

    print(verilog.convert(m, ios={m.dividend_i, m.divisor_i, m.quotient_o, m.valid_i, m.valid_o, m.ce}))