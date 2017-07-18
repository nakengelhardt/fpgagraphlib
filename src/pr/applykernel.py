from migen import *
from migen.genlib.record import *
from tbsupport import convert_32b_int_to_float, convert_int_to_record

from pr.interfaces import payload_layout, node_storage_layout
from faddsub import FAddSub
from fmul import FMul

import logging

total_pr_rounds = 30

class ApplyKernel(Module):
    def __init__(self, addresslayout):
        nodeidsize = addresslayout.nodeidsize
        floatsize = addresslayout.floatsize

        self.nodeid_in = Signal(nodeidsize)
        self.state_in = Record(set_layout_parameters(node_storage_layout, **addresslayout.get_params()))
        self.valid_in = Signal()
        self.round_in = Signal(addresslayout.channel_bits)
        self.barrier_in = Signal()
        self.ready = Signal()

        self.nodeid_out = Signal(nodeidsize)
        self.state_out = Record(set_layout_parameters(node_storage_layout, **addresslayout.get_params()))
        self.state_valid = Signal()
        self.state_barrier = Signal()

        self.update_out = Record(set_layout_parameters(payload_layout, **addresslayout.get_params()))
        self.update_sender = Signal(nodeidsize)
        self.update_valid = Signal()
        self.update_round = Signal(addresslayout.channel_bits)
        self.barrier_out = Signal()
        self.update_ack = Signal()



        ###

        # float constants
        const_base = Signal(floatsize)
        self.comb += const_base.eq(addresslayout.const_base) # init to 0.15/num_nodes
        const_0_85 = Signal(floatsize)
        self.comb += const_0_85.eq(0x3f59999a)

        p2_ce = Signal()

        self.comb += p2_ce.eq(self.update_ack)
        self.comb += self.ready.eq(p2_ce)

        self.sync += If(p2_ce,
            self.nodeid_out.eq(self.nodeid_in),
            self.state_out.nneighbors.eq(self.state_in.nneighbors),
            self.state_out.nrecvd.eq(0),
            self.state_out.sum.eq(0),
            self.state_out.active.eq(0),
            self.state_valid.eq(self.valid_in),
            self.state_barrier.eq(self.barrier_in)
        )

        # Second part: If at end, then multiply by 0.85 and add to const_base and send as message
        # 6 + 4 cycles latency

        dyn_rank = Signal(floatsize)
        dyn_rank_valid = Signal()

        self.submodules.mul = FMul()

        self.comb += [
            self.mul.a.eq(self.state_in.sum),
            self.mul.b.eq(const_0_85),
            self.mul.valid_i.eq(self.valid_in),
            dyn_rank.eq(self.mul.r),
            dyn_rank_valid.eq(self.mul.valid_o),
            self.mul.ce.eq(p2_ce)
        ]

        self.submodules.add2 = FAddSub()

        self.comb += [
            self.add2.a.eq(const_base),
            self.add2.b.eq(dyn_rank),
            self.add2.valid_i.eq(dyn_rank_valid),
            self.update_out.weight.eq(self.add2.r),
            self.update_valid.eq(self.add2.valid_o),
            self.add2.ce.eq(p2_ce)
        ]

        m_sender = [Signal(nodeidsize) for _ in range(10)]
        m_barrier = [Signal() for _ in range(10)]
        m_round = [Signal(addresslayout.channel_bits) for _ in range(10)]

        self.sync += If(p2_ce, [
            m_sender[0].eq(self.nodeid_in),
            m_barrier[0].eq(self.barrier_in),
            m_round[0].eq(self.round_in)
        ] + [
            m_sender[i].eq(m_sender[i-1]) for i in range(1,10)
        ] + [
            m_barrier[i].eq(m_barrier[i-1]) for i in range(1,10)
        ] + [
            m_round[i].eq(m_round[i-1]) for i in range(1,10)
        ])

        self.comb += [
            self.barrier_out.eq(m_barrier[-1]),
            self.update_sender.eq(m_sender[-1]),
            self.update_round.eq(m_round[-1])
        ]

    def gen_selfcheck(self, tb):
        logger = logging.getLogger("simulation.applykernel")
        num_pe = len(tb.apply)
        num_nodes_per_pe = tb.addresslayout.num_nodes_per_pe
        pe_id = [a.applykernel for a in tb.apply].index(self)
        state_level = 0
        out_level = 0
        in_level = 0
        num_cycles = 0
        num_messages_in = 0
        num_messages_out = 0
        while not (yield tb.global_inactive):
            num_cycles += 1
            if (yield self.state_barrier):
                assert(not (yield self.state_valid))
                state_level += 1
                logger.info("{}: PE {} raised to level {}".format(num_cycles, pe_id, state_level))
                if state_level < total_pr_rounds:
                    for node in range(num_nodes_per_pe):
                        data = (yield tb.apply[pe_id].mem[node])
                        s = convert_int_to_record(data, set_layout_parameters(node_storage_layout, **tb.addresslayout.get_params()))
                        if s['nrecvd'] != 0:
                            logger.warning("{}: node {} did not update correctly in round {}! ({} out of {} messages received) / raw: {}".format(num_cycles, pe_id*num_nodes_per_pe+node, state_level, s['nrecvd'], s['nneighbors'], hex(data)))
            if (yield self.barrier_out) and (yield self.update_ack):
                out_level += 1
                if (yield self.update_valid):
                    logger.warning("{}: valid and barrier raised simultaneously on applykernel output on PE {}".format(num_cycles, pe_id))
            if (yield self.update_valid) and (yield self.update_ack):
                num_messages_out += 1
                logger.debug("{}: Node {} updated in round {}. New weight: {}".format(num_cycles, (yield self.update_sender), out_level, convert_32b_int_to_float((yield self.update_out.weight))))
                if out_level >= total_pr_rounds:
                    logger.warning("{}: message sent after inactivity level reached".format(num_cycles))
            if (yield self.barrier_in) and (yield self.ready):
                in_level += 1
            if (yield self.valid_in) and (yield self.ready):
                num_messages_in += 1
                if (yield self.barrier_in):
                    logger.warning("{}: valid and barrier raised simultaneously on applykernel input on PE {}".format(num_cycles, pe_id))
                if in_level == 0:
                    logger.debug("{}: Init message for node {}".format(num_cycles, (yield self.nodeid_in)))
                else:
                    logger.debug("{}: Message {} of {} for node {} from node {}".format(num_cycles, (yield self.state_in.nrecvd)+1, (yield self.state_in.nneighbors), (yield self.nodeid_in), (yield self.sender_in)))
            yield
        logger.info("PE {}: {} cycles taken for {} supersteps. {} messages received, {} messages sent.".format(pe_id, num_cycles, state_level, num_messages_in, num_messages_out))
        logger.info("Average throughput: In: {:.1f} cycles/message Out: {:.1f} cycles/message".format(num_cycles/num_messages_in if num_messages_in!=0 else 0, num_cycles/num_messages_out if num_messages_out!=0 else 0))
