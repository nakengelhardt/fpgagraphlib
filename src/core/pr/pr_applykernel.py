from migen import *
from migen.genlib.record import *
from tbsupport import convert_32b_int_to_float

from pr.interfaces import payload_layout, node_storage_layout, convert_int_to_record
from faddsub import FAddSub
from fmul import FMul

class ApplyKernel(Module):
    def __init__(self, addresslayout):
        nodeidsize = addresslayout.nodeidsize
        floatsize = addresslayout.floatsize

        self.level_in = Signal(32)
        self.nodeid_in = Signal(nodeidsize)
        self.sender_in = Signal(nodeidsize)
        self.message_in = Record(set_layout_parameters(payload_layout, **addresslayout.get_params()))
        self.state_in = Record(set_layout_parameters(node_storage_layout, **addresslayout.get_params()))
        self.valid_in = Signal()
        self.barrier_in = Signal()
        self.ready = Signal()

        self.nodeid_out = Signal(nodeidsize)
        self.state_out = Record(set_layout_parameters(node_storage_layout, **addresslayout.get_params()))
        self.state_valid = Signal()
        self.state_barrier = Signal()

        self.message_out = Record(set_layout_parameters(payload_layout, **addresslayout.get_params()))
        self.message_sender = Signal(nodeidsize)
        self.message_valid = Signal()
        self.barrier_out = Signal()
        self.message_ack = Signal()

        

        ###

        # float constants
        const_base = Signal(floatsize)
        self.comb += const_base.eq(addresslayout.const_base) # init to 0.15/num_nodes
        const_0_85 = Signal(floatsize)
        self.comb += const_0_85.eq(0x3f59999a)
        
        p1_ce = Signal()

        self.comb += self.ready.eq(p1_ce)

        # First part: add weight to sum
        # 4 cycles latency
        n_nodeid = Signal(nodeidsize)
        n_sum = Signal(floatsize)
        n_nrecvd = Signal(nodeidsize)
        n_nneighbors = Signal(nodeidsize)
        n_barrier = Signal()
        n_valid = Signal()
        n_allrecvd = Signal()
        n_init = Signal()
        n_notend = Signal()
        nodeweight = Signal(floatsize)

        self.submodules.add1 = FAddSub()
        self.comb += [
            self.add1.a.eq(self.state_in.sum),
            self.add1.b.eq(self.message_in.weight),
            self.add1.valid_i.eq(self.valid_in),
            n_sum.eq(self.add1.r),
            n_valid.eq(self.add1.valid_o),
            self.add1.ce.eq(p1_ce)
        ]

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
            self.state_barrier.eq(n_barrier),
            self.nodeid_out.eq(n_nodeid),
            self.state_out.nneighbors.eq(n_nneighbors),
            If(send_message,
                self.state_out.nrecvd.eq(0),
                self.state_out.sum.eq(0)
            ).Else(
                self.state_out.nrecvd.eq(n_nrecvd),
                self.state_out.sum.eq(n_sum)
            ),
            self.state_valid.eq(n_valid & p1_ce),
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
        dyn_rank = Signal(floatsize)
        dyn_rank_valid = Signal()

        self.submodules.mul = FMul()

        self.comb += [
            self.mul.a.eq(nodeweight), 
            self.mul.b.eq(const_0_85), 
            self.mul.valid_i.eq(send_message), 
            dyn_rank.eq(self.mul.r), 
            dyn_rank_valid.eq(self.mul.valid_o), 
            self.mul.ce.eq(p2_ce)
        ]

        self.submodules.add2 = FAddSub()
        
        self.comb += [
            self.add2.a.eq(const_base),
            self.add2.b.eq(dyn_rank),
            self.add2.valid_i.eq(dyn_rank_valid),
            self.message_out.weight.eq(self.add2.r),
            self.message_valid.eq(self.add2.valid_o),
            self.add2.ce.eq(p2_ce)
        ]

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

    def gen_selfcheck(self, tb, quiet=False):
        num_pe = len(tb.apply)
        num_nodes_per_pe = tb.addresslayout.num_nodes_per_pe
        pe_id = [a.applykernel for a in tb.apply].index(self)
        in_level = 0
        out_level = 0
        num_cycles = 0
        grace_cycles_left = 12
        while not (yield tb.global_inactive):
            num_cycles += 1
            if (yield self.state_barrier):
                assert(not (yield self.state_valid))
                in_level += 1
                print("{}\tPE {} raised to level {}".format(num_cycles, pe_id, in_level))
                if in_level < 30:
                    for node in range(num_nodes_per_pe):
                        data = (yield tb.apply[pe_id].mem[node])
                        s = convert_int_to_record(data, set_layout_parameters(node_storage_layout, **tb.addresslayout.get_params()))
                        if s['nrecvd'] != 0:
                            print("{}\tWarning: node {} did not update correctly in round {}! ({} out of {} messages received) / raw: {}".format(num_cycles, pe_id*num_nodes_per_pe+node, in_level, s['nrecvd'], s['nneighbors'], hex(data)))
            if (yield self.barrier_out) and (yield self.message_ack):
                out_level += 1
            if out_level >= 30:
                if (yield self.message_valid) and (yield self.message_ack):
                    print("{}\tWarning: message sent after inactivity in_level reached".format(num_cycles))
            if not quiet:
                if (yield self.valid_in) and (yield self.ready) and not (yield self.barrier_in):
                    if in_level == 0:
                        print("{}\tInit message for node {}".format(num_cycles, (yield self.nodeid_in)))
                    else:
                        print("{}\tMessage {} of {} for node {} from node {}".format(num_cycles, (yield self.state_in.nrecvd)+1, (yield self.state_in.nneighbors), (yield self.nodeid_in), (yield self.sender_in)))
                if (yield self.message_valid) and (yield self.message_ack):
                    print("{}\tNode {} updated in round {}. New weight: {}".format(num_cycles, (yield self.message_sender), out_level, convert_32b_int_to_float((yield self.message_out.weight))))
            yield
        print(str(num_cycles) + " cycles taken.")
