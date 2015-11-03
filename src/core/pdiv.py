from migen import *

class Divider(Module):
	"""Pipelined integer division. Result is ready w+1 cycles after input is presented."""
	def __init__(self, w):
		self.dividend_i = Signal(w)
		self.divisor_i = Signal(w)
		self.valid_i = Signal()
		self.quotient_o = Signal(w)
		self.remainder_o = Signal(w)
		self.valid_o = Signal()

		###

		qr = [Signal(2*w) for _ in range(w+1)]
		divisor_r = [Signal(w) for _ in range(w+1)]
		diff = [Signal(w+1) for _ in range(w+1)]
		valid = [Signal() for _ in range(w+1)]

		self.sync += [
			qr[0].eq(self.dividend_i),
			divisor_r[0].eq(self.divisor_i),
			valid[0].eq(self.valid_i)
		]

		for stage in range(w):
			self.comb += diff[stage].eq(qr[stage][w-1:] - divisor_r[stage])

		for stage in range(1, w+1):
			self.sync += [
				divisor_r[stage].eq(divisor_r[stage - 1]),
				If(diff[stage - 1][w],
					qr[stage].eq(Cat(0, qr[stage - 1][:2*w-1]))
				).Else(
					qr[stage].eq(Cat(1, qr[stage - 1][:w-1], diff[stage - 1][:w]))
				),
				valid[stage].eq(valid[stage - 1])
			]

		self.comb += [
			self.quotient_o.eq(qr[w][:w]),
			self.remainder_o.eq(qr[w][w:]),
			self.valid_o.eq(valid[w])
		]