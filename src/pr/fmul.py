from migen.fhdl.std import *

@CEInserter()
class FMul(Module):
	def __init__(self):
		self.a = Signal(32)
		self.b = Signal(32)
		self.valid_i = Signal()
		self.r = Signal(32)
		self.valid_o = Signal()

		###

		a_sign = Signal()
		a_expn = Signal(8)
		a_mant = Signal(24)
		b_sign = Signal()
		b_expn = Signal(8)
		b_mant = Signal(24)
		r_zero = Signal()
		r_sign = Signal()
		r_expn = Signal(8)
		r_a_mant = Signal(24)
		r_b_mant = Signal(24)
		r_valid = Signal()

		self.comb += [
			a_sign.eq(self.a[31]),
			a_expn.eq(self.a[23:31]),
			a_mant.eq(Cat(self.a[0:23], 1)),
			b_sign.eq(self.b[31]),
			b_expn.eq(self.b[23:31]),
			b_mant.eq(Cat(self.b[0:23], 1))
		]

		# Stage 1
		self.sync += [
			r_valid.eq(self.valid_i),
			r_zero.eq((a_expn == 0) | (b_expn == 0)),
			r_sign.eq(a_sign ^ b_sign),
			r_expn.eq(a_expn + b_expn - 127),
			r_a_mant.eq(a_mant),
			r_b_mant.eq(b_mant)
		]

		# Stage 2
		r1_zero = Signal()
		r1_sign = Signal()
		r1_expn = Signal(8)
		r1_mant = Signal(48)
		r1_valid = Signal()

		self.sync += [
			r1_valid.eq(r_valid),
			r1_zero.eq(r_zero),
			r1_sign.eq(r_sign),
			r1_expn.eq(r_expn),
			r1_mant.eq(r_a_mant*r_b_mant)
		]

		# Stage 3
		r2_zero = Signal()
		r2_sign = Signal()
		r2_expn = Signal(8)
		r2_mant = Signal(48)
		r2_valid = Signal()

		self.sync += [
			r2_valid.eq(r1_valid),
			r2_zero.eq(r1_zero),
			r2_sign.eq(r1_sign),
			r2_expn.eq(r1_expn),
			r2_mant.eq(r1_mant)
		]

		# Stage 4
		r3_zero = Signal()
		r3_sign = Signal()
		r3_expn = Signal(8)
		r3_mant = Signal(48)
		r3_valid = Signal()

		self.sync += [
			r3_valid.eq(r2_valid),
			r3_zero.eq(r2_zero),
			r3_sign.eq(r2_sign),
			r3_expn.eq(r2_expn),
			r3_mant.eq(r2_mant)
		]

		# Stage 5
		r4_zero = Signal()
		r4_sign = Signal()
		r4_expn = Signal(8)
		r4_mant = Signal(48)
		r4_valid = Signal()

		self.sync += [
			r4_valid.eq(r3_valid),
			r4_zero.eq(r3_zero),
			r4_sign.eq(r3_sign),
			r4_expn.eq(r3_expn),
			r4_mant.eq(r3_mant)
		]

		# Stage 6
		self.sync += [
			self.valid_o.eq(r4_valid),
			If(r4_zero,
				self.r.eq(0)
			).Else(
				If(~r4_mant[47],
					self.r.eq(Cat(r4_mant[23:46], r4_expn, r4_sign))
				).Else(
					self.r.eq(Cat(r4_mant[24:47], r4_expn+1, r4_sign))
				)
			)
		]

if __name__ == "__main__":
	from migen.fhdl import verilog

	m = FMul()

	print(verilog.convert(m, ios={m.a, m.b, m.valid_i, m.r, m.valid_o, m.ce}))