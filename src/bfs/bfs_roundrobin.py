from migen.fhdl.std import *

(SP_WITHDRAW, SP_CE) = range(2)

class BFSRoundRobin(Module):
	def __init__(self, n, switch_policy=SP_WITHDRAW):
		self.request = Signal(n)
		self.last = Signal(max=max(2, n))
		self.next = Signal(max=max(2, n))
		self.switch_policy = switch_policy
		if self.switch_policy == SP_CE:
			self.ce = Signal()

		###


		if n > 1:
			cases = {}
			for i in range(n):
				switch = []
				for j in reversed(range(i+1,i+n)):
					t = j % n
					switch = [
						If(self.request[t],
							self.next.eq(t)
						).Else(
							*switch
						)
					]
				if self.switch_policy == SP_WITHDRAW:
					case = [If(~self.request[i], *switch)]
				else:
					case = switch
				cases[i] = case
			statement = self.next.eq(self.last), Case(self.last, cases)
			self.comb += statement
			if self.switch_policy == SP_CE:
				self.sync += If(self.ce, self.last.eq(self.next))
			else:
				self.sync += self.last.eq(self.next)
		else:
			self.comb += self.last.eq(0)
