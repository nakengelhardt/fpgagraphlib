from migen.fhdl.std import *
from migen.genlib.record import *

from pr_interfaces import node_storage_layout, payload_layout
from faddsub import FAddSub
from fmul import FMul

class PRApplyKernel(Module):
	def __init__(self, addresslayout):
		nodeidsize = addresslayout.nodeidsize
		fixedptfloatsize = addresslayout.fixedptfloatsize
		fixedptdecimals = addresslayout.fixedptdecimals

		self.level_in = Signal(32)
		self.nodeid_in = Signal(nodeidsize)
		self.message_in = Record(set_layout_parameters(payload_layout, **addresslayout.get_params()))
		self.state_in = Record(set_layout_parameters(node_storage_layout, **addresslayout.get_params()))
		self.valid_in = Signal()
		self.barrier_in = Signal()
		self.ready = Signal()

		self.nodeid_out = Signal(nodeidsize)
		self.state_out = Record(set_layout_parameters(node_storage_layout, **addresslayout.get_params()))
		self.state_valid = Signal()

		self.message_out = Record(set_layout_parameters(payload_layout, **addresslayout.get_params()))
		self.message_sender = Signal(nodeidsize)
		self.message_valid = Signal()
		self.barrier_out = Signal()
		self.message_ack = Signal()

		

		###

		# float constants
		const_base = Signal(fixedptfloatsize)
		self.comb += const_base.eq(addresslayout.const_base) # init to 0.15/num_nodes
		const_0_85 = Signal(fixedptfloatsize)
		self.comb += const_0_85.eq(0x3f59999a)
		
		p1_ce = Signal()

		self.comb += self.ready.eq(p1_ce)

		# First part: add weight to sum
		# 4 cycles latency
		n_nodeid = Signal(nodeidsize)
		n_sum = Signal(fixedptfloatsize)
		n_nrecvd = Signal(nodeidsize)
		n_nneighbors = Signal(nodeidsize)
		n_barrier = Signal()
		n_valid = Signal()
		n_allrecvd = Signal()
		n_init = Signal()
		n_notend = Signal()
		nodeweight = Signal(fixedptfloatsize)

		self.submodules += FAddSub(a=self.state_in.sum, b=self.message_in.weight, valid_i=self.valid_in, r=n_sum, valid_o=n_valid, ce=p1_ce)
		
		i_nrecvd = [Signal(nodeidsize) for _ in range(3)]
		i_nneighbors = [Signal(nodeidsize) for _ in range(3)]
		i_barrier = [Signal() for _ in range(3)]
		i_nodeid = [Signal(nodeidsize) for _ in range(3)]
		i_init = [Signal() for _ in range(3)]
		i_notend = [Signal() for _ in range(3)]

		self.sync += If(p1_ce, [
			i_nrecvd[0].eq(self.state_in.nrecvd + 1),
			i_nneighbors[0].eq(self.state_in.nneighbors),
			i_barrier[0].eq(self.barrier_in),
			i_nodeid[0].eq(self.nodeid_in),
			i_init[0].eq(self.level_in == 0),
			i_notend[0].eq(self.level_in < 30)
		] + [
			i_nrecvd[i].eq(i_nrecvd[i-1]) for i in range(1,3)
		] + [
			i_nneighbors[i].eq(i_nneighbors[i-1]) for i in range(1,3)
		] + [
			i_barrier[i].eq(i_barrier[i-1]) for i in range(1,3)
		] + [
			i_nodeid[i].eq(i_nodeid[i-1]) for i in range(1,3)
		] + [
			i_init[i].eq(i_init[i-1]) for i in range(1,3)
		] + [
			i_notend[i].eq(i_notend[i-1]) for i in range(1,3)
		] + [
			n_nrecvd.eq(i_nrecvd[-1]),
			n_nneighbors.eq(i_nneighbors[-1]),
			n_barrier.eq(i_barrier[-1]),
			n_nodeid.eq(i_nodeid[-1]),
			n_allrecvd.eq(i_nrecvd[-1] == i_nneighbors[-1]),
			n_init.eq(i_init[-1]),
			n_notend.eq(i_notend[-1])
		])

		send_message = Signal()

		self.comb += [
			self.nodeid_out.eq(n_nodeid),
			self.state_out.nneighbors.eq(n_nneighbors),
			If(send_message,
				self.state_out.nrecvd.eq(0),
				self.state_out.sum.eq(0)
			).Else(
				self.state_out.nrecvd.eq(n_nrecvd),
				self.state_out.sum.eq(n_sum)
			),
			self.state_valid.eq(n_valid),
			send_message.eq((n_allrecvd | n_init) & n_valid & n_notend),
			If(n_init,
				nodeweight.eq(0)
			).Else(
				nodeweight.eq(n_sum)
			)
		]

		p2_ce = Signal()

		self.comb += p1_ce.eq(p2_ce | ~n_allrecvd)
		self.comb += p2_ce.eq(self.message_ack)

		# Second part: If at end, then multiply by 0.85 and add to const_base and send as message
		# 6 + 4 cycles latency
		dyn_rank = Signal(fixedptfloatsize)
		dyn_rank_valid = Signal()

		self.submodules += FMul(a=nodeweight, b=const_0_85, valid_i=send_message, r=dyn_rank, valid_o=dyn_rank_valid)

		self.submodules += FAddSub(a=const_base, b=dyn_rank, valid_i=dyn_rank_valid, r=self.message_out.weight, valid_o=self.message_valid)
		
		m_sender = [Signal(nodeidsize) for _ in range(10)]
		m_barrier = [Signal() for _ in range(10)]

		self.sync += If(p2_ce, [
			m_sender[0].eq(n_nodeid),
			m_barrier[0].eq(n_barrier)
		] + [
			m_sender[i].eq(m_sender[i-1]) for i in range(1,10)
		] + [
			m_barrier[i].eq(m_barrier[i-1]) for i in range(1,10)
		])

		self.comb += [
			self.barrier_out.eq(m_barrier[-1]),
			self.message_sender.eq(m_sender[-1])
		]

