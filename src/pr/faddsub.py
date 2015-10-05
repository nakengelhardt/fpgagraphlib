from migen.fhdl.std import *
from migen.genlib.coding import PriorityEncoder

@CEInserter()
class FAddSub(Module):
	def __init__(self):

		self.a = Signal(32)
		self.b = Signal(32)
		self.valid_i = Signal()
		self.r = Signal(32)
		self.valid_o = Signal()
		self.sub = Signal()

		# Stage 1 #
		s1_valid = Signal()
		a_sign = Signal()
		a_expn = Signal(8)
		a_mant = Signal(23)

		b_sign = Signal()
		b_expn = Signal(8)
		b_mant = Signal(23)

		self.sync += [
			s1_valid.eq(self.valid_i),
			a_sign.eq(self.a[31]),
			a_expn.eq(self.a[23:31]),
			a_mant.eq(self.a[0:23]),

			b_sign.eq(self.b[31] ^ self.sub),
			b_expn.eq(self.b[23:31]),
			b_mant.eq(self.b[0:23]),
		]

		# Stage 2 #
		s2_iszero = Signal()		# one or both of the operands is zero 
		s2_sign = Signal()			# sign of the result 
		s2_issub = Signal()			# shall we do a subtraction or an addition 
		s2_expn_max = Signal(8)		# exponent of the bigger number (abs value) 
		s2_expn_diff = Signal(8)	# difference with the exponent of the smaller number (abs value) 
		s2_mant_max = Signal(23)	# mantissa of the bigger number (abs value) 
		s2_mant_min = Signal(23)	# mantissa of the smaller number (abs value) 

		s2_valid = Signal()

		expn_compare = Signal()
		expn_equal = Signal()
		mant_compare = Signal()

		self.comb += [
			expn_compare.eq(a_expn > b_expn),
			expn_equal.eq(a_expn == b_expn),
			mant_compare.eq(a_mant > b_mant),
		]

		self.sync += [
			s2_valid.eq(s1_valid),
			s2_issub.eq(a_sign ^ b_sign),	
			If(expn_compare,
				# |b|.eq(|a|
				s2_sign.eq(a_sign)
			).Else(
				If(expn_equal,
					If(mant_compare,
						# |b|.eq(|a|
						s2_sign.eq(a_sign)
					).Else(
						# |b| >  |a|
						s2_sign.eq(b_sign)
					)
				).Else(
					# |b| >  |a|
					s2_sign.eq(b_sign)
				)
			),
			If(expn_compare,
				s2_expn_max.eq(a_expn),
				s2_expn_diff.eq(a_expn - b_expn)
			).Else(
				s2_expn_max.eq(b_expn),
				s2_expn_diff.eq(b_expn - a_expn)
			),
			If(expn_equal,
				If(mant_compare,
					s2_mant_max.eq(a_mant),
					s2_mant_min.eq(b_mant)
				).Else(
					s2_mant_max.eq(b_mant),
					s2_mant_min.eq(a_mant)
				)
			).Else(
				If(expn_compare,
					s2_mant_max.eq(a_mant),
					s2_mant_min.eq(b_mant)
				).Else(
					s2_mant_max.eq(b_mant),
					s2_mant_min.eq(a_mant)
				)
			),
			s2_iszero.eq((a_expn == 0)|(b_expn == 0))
		]

		# Stage 3

		s3_sign = Signal()
		s3_expn = Signal(8)
		s3_mant = Signal(26)

		s3_valid = Signal()

		# local signals
		max_expanded = Signal(25)
		min_expanded = Signal(25)

		self.comb += [
			max_expanded.eq(Cat(0, s2_mant_max, 1)), # 1 guard digit
			min_expanded.eq(Cat(0, s2_mant_min, 1) >> s2_expn_diff)
		]

		self.sync += [
			s3_valid.eq(s2_valid),
			s3_sign.eq(s2_sign),
			s3_expn.eq(s2_expn_max),
			If(s2_iszero,
				s3_mant.eq(Cat(0, s2_mant_max, 1, 0))
			).Elif(s2_issub,
				s3_mant.eq(max_expanded - min_expanded)
			).Else(
				s3_mant.eq(max_expanded + min_expanded)
			)
		]

		# Stage 4

		s4_sign = Signal()
		s4_expn = Signal(8)
		s4_mant = Signal(26)

		clz = Signal(5)

		pe = PriorityEncoder(26)
		self.submodules += pe

		self.comb += pe.i.eq(s3_mant[::-1]), clz.eq(pe.o)

		self.sync += [
			self.valid_o.eq(s3_valid),
			s4_sign.eq(s3_sign),
			s4_mant.eq(s3_mant << clz),
			s4_expn.eq(s3_expn - clz + 1)
		]

		self.comb += self.r.eq(Cat(s4_mant[2:25], s4_expn, s4_sign))

if __name__ == "__main__":
	from migen.fhdl import verilog

	m = FAddSub()

	print(verilog.convert(m, ios={m.a, m.b, m.r, m.valid_i, m.valid_o, m.sub, m.ce}))