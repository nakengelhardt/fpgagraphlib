from migen import *
from migen.genlib.record import *
from tbsupport import convert_32b_int_to_float, convert_int_to_record

from pr.interfaces import *
from faddsub import FAddSub
from fmul import FMul

import logging

class ApplyKernel(Module):
    # PageRank formula:
    # PR_(i+1)(u) = (1-d)/N + d * sum(PR_i(v)/degree(v) for v in neighbors(u))
    # the apply phase performs (1-d)/N + d * sum
    # initial PR in first round should be 1/N; therefore sum must be initialized to d/N
    def __init__(self, config):
        nodeidsize = config.addresslayout.nodeidsize
        floatsize = config.addresslayout.floatsize

        self.level_in = Signal(32)
        self.nodeid_in = Signal(nodeidsize)
        self.state_in = Record(set_layout_parameters(node_storage_layout, **config.addresslayout.get_params()))
        self.state_in_valid = Signal()
        self.valid_in = Signal()
        self.round_in = Signal(config.addresslayout.channel_bits)
        self.barrier_in = Signal()
        self.ready = Signal()

        self.nodeid_out = Signal(nodeidsize)
        self.state_out = Record(set_layout_parameters(node_storage_layout, **config.addresslayout.get_params()))
        self.state_valid = Signal()
        self.state_barrier = Signal()
        self.state_ack = Signal()

        self.update_out = Record(set_layout_parameters(update_layout, **config.addresslayout.get_params()))
        self.update_sender = Signal(nodeidsize)
        self.update_valid = Signal()
        self.update_round = Signal(config.addresslayout.channel_bits)
        self.barrier_out = Signal()
        self.update_ack = Signal()

        self.kernel_error = Signal()

        ###

        # float constants
        const_base = Signal(floatsize)
        self.comb += const_base.eq(config.const_base) # init to 0.15/num_nodes
        const_0_85 = Signal(floatsize)
        self.comb += const_0_85.eq(0x3f59999a)

        self.comb += self.ready.eq(self.update_ack & self.state_ack)

        self.sync += If(self.ready,
            self.nodeid_out.eq(self.nodeid_in),
            self.state_out.nneighbors.eq(self.state_in.nneighbors),
            self.state_out.nrecvd.eq(0),
            self.state_out.sum.eq(0),
            self.state_out.active.eq(0),
            self.state_barrier.eq(self.barrier_in),
            If(self.valid_in & self.state_in.active & (self.state_in.nrecvd != self.state_in.nneighbors),
                self.kernel_error.eq(1)
            )
        )

        self.sync += self.state_valid.eq(self.valid_in & self.state_in_valid & self.update_ack)

        # Second part: If at end, then multiply by 0.85 and add to const_base and send as message
        # 6 + 4 cycles latency

        send_update = self.state_in.active & (self.level_in < config.total_pr_rounds)

        self.submodules.mul = FMul()

        self.comb += [
            self.mul.a.eq(self.state_in.sum),
            self.mul.b.eq(const_0_85),
            self.mul.valid_i.eq(self.valid_in & (send_update | self.barrier_in)),
            self.mul.ce.eq(self.ready)
        ]

        self.submodules.add = FAddSub()

        self.comb += [
            self.add.a.eq(const_base),
            self.add.b.eq(self.mul.r),
            self.add.valid_i.eq(self.mul.valid_o),
            self.update_out.rank.eq(self.add.r),
            self.update_valid.eq(self.add.valid_o & self.state_ack),
            self.add.ce.eq(self.ready)
        ]

        m_sender = [Signal(nodeidsize) for _ in range(10)]
        m_barrier = [Signal() for _ in range(10)]
        m_round = [Signal(config.addresslayout.channel_bits) for _ in range(10)]

        self.sync += If(self.ready, [
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
        logger = logging.getLogger("sim.applykernel")
        num_nodes_per_pe = tb.config.addresslayout.num_nodes_per_pe
        num_pe = tb.config.addresslayout.num_pe
        pe_id = [a.gatherapplykernel.applykernel for core in tb.cores for a in core.apply].index(self)
        applys = [a for core in tb.cores for a in core.apply]
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
            if (yield self.update_valid) and (yield self.update_ack):
                if (yield self.barrier_out):
                    out_level += 1
                else:
                    num_messages_out += 1
                    logger.debug("{}: Node {} updated in round {}. New rank: {}".format(num_cycles, (yield self.update_sender), out_level, convert_32b_int_to_float((yield self.update_out.rank))))
                    if out_level >= tb.config.total_pr_rounds:
                        logger.warning("{}: message sent after inactivity level reached".format(num_cycles))
            if (yield self.valid_in) and (yield self.ready):
                if (yield self.barrier_in):
                    in_level += 1
                else:
                    node = tb.config.addresslayout.local_adr((yield self.nodeid_in))
                    data = (yield applys[pe_id].mem[node])
                    s = convert_int_to_record(data, set_layout_parameters(node_storage_layout, **tb.config.addresslayout.get_params()))
                    num_messages_in += s['nrecvd']
                    if s['nrecvd'] != s['nneighbors']:
                        logger.warning("{}: node {} did not update correctly in round {}! ({} out of {} messages received) / raw: {}".format(num_cycles, pe_id*num_nodes_per_pe+node, state_level, s['nrecvd'], s['nneighbors'], hex(data)))
            yield
        logger.info("PE {}: {} cycles taken for {} supersteps. {} messages received, {} updates sent.".format(pe_id, num_cycles, state_level, num_messages_in, num_messages_out))
        logger.info("Average throughput: In: {:.1f} cycles/message Out: {:.1f} cycles/message".format(num_cycles/num_messages_in if num_messages_in!=0 else 0, num_cycles/num_messages_out if num_messages_out!=0 else 0))
        if (yield self.kernel_error):
            logger.error("PE {} reports kernel_error")
