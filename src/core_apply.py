from migen import *
from migen.genlib.record import *
from recordfifo import *
from tbsupport import *

from core_interfaces import ApplyInterface, ScatterInterface, Message
from core_collision import CollisionDetector
from hmc_backed_fifo import HMCBackedFIFO

class Apply(Module):
    def __init__(self, config, pe_id):
        self.config = config
        self.pe_id = pe_id
        addresslayout = config.addresslayout
        nodeidsize = addresslayout.nodeidsize
        num_nodes_per_pe = addresslayout.num_nodes_per_pe

        # input Q interface
        self.apply_interface = ApplyInterface(**addresslayout.get_params())

        # scatter interface
        # send self.update message to all neighbors
        # message format (sending_node_id) (normally would be (sending_node_id, weight), but for PR weight = sending_node_id)
        self.scatter_interface = ScatterInterface(**addresslayout.get_params())

        ####

        apply_interface_in_fifo = InterfaceFIFO(layout=self.apply_interface.layout, depth=8)
        self.submodules += apply_interface_in_fifo
        self.comb += self.apply_interface.connect(apply_interface_in_fifo.din)

        # local node data storage
        self.specials.mem = Memory(layout_len(addresslayout.node_storage_layout), max(2, len(config.adj_idx[pe_id])+1), init=config.init_nodedata[pe_id] if config.init_nodedata else None, name="vertex_data_{}".format(self.pe_id))
        rd_port = self.specials.rd_port = self.mem.get_port(has_re=True)
        wr_port = self.specials.wr_port = self.mem.get_port(write_capable=True)

        local_wr_port = Record(layout=get_mem_port_layout(wr_port))
        self.external_wr_port = Record(layout=get_mem_port_layout(wr_port) + [("select", 1)])

        self.comb += [
            If(self.external_wr_port.select,
                self.external_wr_port.connect(wr_port, omit={"select"})
            ).Else(
                local_wr_port.connect(wr_port)
            )
        ]

        # detect termination (now done by collating votes to halt in barriercounter - if barrier is passed on with halt bit set, don't propagate)
        self.inactive = Signal()
        self.sync += If(apply_interface_in_fifo.dout.valid & apply_interface_in_fifo.dout.ack & apply_interface_in_fifo.dout.msg.barrier & apply_interface_in_fifo.dout.msg.halt,
            self.inactive.eq(1)
        )

        # should pipeline advance?
        upstream_ack = Signal()
        collision_re = Signal()
        collision_en = Signal()

        # count levels
        self.level = Signal(8)

        ## Stage 1
        # rename some signals for easier reading, separate barrier and normal valid (for writing to state mem)
        dest_node_id = Signal(nodeidsize)
        sender = Signal(nodeidsize)
        payload = Signal(addresslayout.payloadsize)
        roundpar = Signal(config.addresslayout.channel_bits)
        valid = Signal()
        barrier = Signal()

        self.comb += [
            dest_node_id.eq(apply_interface_in_fifo.dout.msg.dest_id),
            sender.eq(apply_interface_in_fifo.dout.msg.sender),
            payload.eq(apply_interface_in_fifo.dout.msg.payload),
            roundpar.eq(apply_interface_in_fifo.dout.msg.roundpar),
            valid.eq(apply_interface_in_fifo.dout.valid & ~apply_interface_in_fifo.dout.msg.barrier),
            barrier.eq(apply_interface_in_fifo.dout.valid & apply_interface_in_fifo.dout.msg.barrier & ~apply_interface_in_fifo.dout.msg.halt),
        ]

        ## Stage 2
        dest_node_id2 = Signal(nodeidsize)
        sender2 = Signal(nodeidsize)
        payload2 = Signal(addresslayout.payloadsize)
        roundpar2 = Signal(config.addresslayout.channel_bits)
        valid2 = Signal()
        ready = Signal()

        apply_valid2 = Signal()
        apply_ready = Signal()
        apply_barrier2 = Signal()
        state_barrier = Signal()

        node_idx = Signal(nodeidsize)
        gather_en = Signal()
        gather_done = Signal()

        next_roundpar = Signal(config.addresslayout.channel_bits)
        self.comb += If(roundpar==config.addresslayout.num_channels-1, next_roundpar.eq(0)).Else(next_roundpar.eq(roundpar+1))

        self.submodules.fsm = FSM()
        self.fsm.act("GATHER",
            rd_port.re.eq(upstream_ack),
            apply_interface_in_fifo.dout.ack.eq(upstream_ack),
            rd_port.adr.eq(addresslayout.local_adr(dest_node_id)),
            NextValue(valid2, valid & collision_re), # insert bubble if collision
            If(upstream_ack,
                NextValue(dest_node_id2, dest_node_id),
                NextValue(sender2, sender),
                NextValue(payload2, payload),
                NextValue(roundpar2, roundpar),
                If(barrier,
                    NextValue(valid2, 0), # this should already be the case, just making sure
                    # note to self, check if sythesizer optimizes it away
                    NextValue(roundpar2, next_roundpar),
                    NextState("FLUSH")
                )
            ),
            gather_en.eq(1),
            collision_en.eq(1)
        )
        self.fsm.act("FLUSH",
            rd_port.re.eq(0),
            NextValue(node_idx, pe_id << log2_int(num_nodes_per_pe)),
            apply_interface_in_fifo.dout.ack.eq(0),
            rd_port.adr.eq(addresslayout.local_adr(dest_node_id)),
            If(gather_done,
                NextState("APPLY")
            ),
            gather_en.eq(1)
        )
        self.fsm.act("APPLY",
            rd_port.re.eq(apply_ready),
            apply_interface_in_fifo.dout.ack.eq(0),
            rd_port.adr.eq(addresslayout.local_adr(node_idx)),
            NextValue(apply_valid2, 1),
            If(apply_ready,
                NextValue(dest_node_id2, node_idx),
                NextValue(node_idx, node_idx+1),
                If(node_idx==(len(config.adj_idx[pe_id]) + (pe_id << log2_int(num_nodes_per_pe))),
                    NextValue(apply_barrier2, 1),
                    NextValue(apply_valid2, 0),
                    NextState("BARRIER_SEND")
                )
            )
        )
        self.fsm.act("BARRIER_SEND",
            apply_interface_in_fifo.dout.ack.eq(0),
            rd_port.adr.eq(addresslayout.local_adr(node_idx)),
            If(apply_ready,
                NextValue(apply_barrier2, 0),
                NextState("BARRIER_WAIT")
            )
        )
        self.fsm.act("BARRIER_WAIT",
            If(state_barrier,
                NextValue(self.level, self.level+1),
                NextState("GATHER")
            )
        )

        # collision handling (combinatorial)
        self.submodules.collisiondetector = CollisionDetector(addresslayout)

        self.comb += [
            self.collisiondetector.read_adr.eq(addresslayout.local_adr(dest_node_id)),
            self.collisiondetector.read_adr_valid.eq(valid & collision_en),
            self.collisiondetector.write_adr.eq(local_wr_port.adr),
            self.collisiondetector.write_adr_valid.eq(local_wr_port.we & gather_en),
            collision_re.eq(self.collisiondetector.re),
            gather_done.eq(self.collisiondetector.all_clear)
        ]

        ## Stage 3
        dest_node_id3 = Signal(nodeidsize)
        sender3 = Signal(nodeidsize)
        payload3 = Signal(addresslayout.payloadsize)
        self.roundpar = Signal(config.addresslayout.channel_bits)
        valid3 = Signal()
        data3 = Signal(len(rd_port.dat_r))

        self.submodules.applykernel = config.applykernel(config)
        state_in = Record(addresslayout.node_storage_layout)

        self.sync += [
            If(ready,
                valid3.eq(valid2),
                dest_node_id3.eq(dest_node_id2),
                sender3.eq(sender2),
                payload3.eq(payload2),
                self.roundpar.eq(roundpar2),
                data3.eq(rd_port.dat_r)
            ),
            If(apply_ready,
                self.applykernel.nodeid_in.eq(dest_node_id2),
                self.applykernel.state_in.raw_bits().eq(rd_port.dat_r),
                self.applykernel.round_in.eq(roundpar2),
                self.applykernel.valid_in.eq(state_in.active & apply_valid2),
                self.applykernel.barrier_in.eq(apply_barrier2),
            )
        ]

        downstream_ack = Signal()

        self.comb += [
            state_in.raw_bits().eq(rd_port.dat_r),
            apply_ready.eq(self.applykernel.ready),
            self.applykernel.update_ack.eq(downstream_ack),
            state_barrier.eq(self.applykernel.state_barrier)
        ]

        # User code
        self.submodules.gatherkernel = config.gatherkernel(config)

        self.comb += [
            self.gatherkernel.nodeid_in.eq(dest_node_id3),
            self.gatherkernel.sender_in.eq(sender3),
            self.gatherkernel.message_in.raw_bits().eq(payload3),
            self.gatherkernel.state_in.raw_bits().eq(data3),
            self.gatherkernel.valid_in.eq(valid3),
            self.gatherkernel.level_in.eq(self.level),
            ready.eq(self.gatherkernel.ready),
            upstream_ack.eq(self.gatherkernel.ready & collision_re),
            self.gatherkernel.state_ack.eq(gather_en)
        ]

        # write state updates
        self.comb += If(gather_en,
            local_wr_port.adr.eq(addresslayout.local_adr(self.gatherkernel.nodeid_out)),
            local_wr_port.dat_w.eq(self.gatherkernel.state_out.raw_bits()),
            local_wr_port.we.eq(self.gatherkernel.state_valid)
        ).Else(
            local_wr_port.adr.eq(addresslayout.local_adr(self.applykernel.nodeid_out)),
            local_wr_port.dat_w.eq(self.applykernel.state_out.raw_bits()),
            local_wr_port.we.eq(self.applykernel.state_valid)
        )

        # output handling
        _layout = [
        ( "barrier", 1, DIR_M_TO_S ),
        ( "roundpar", config.addresslayout.channel_bits, DIR_M_TO_S ),
        ( "sender", "nodeidsize", DIR_M_TO_S ),
        ( "msg" , addresslayout.payloadsize, DIR_M_TO_S )
        ]
        outfifo_in = Record(set_layout_parameters(_layout, **addresslayout.get_params()))
        outfifo_out = Record(set_layout_parameters(_layout, **addresslayout.get_params()))
        self.submodules.outfifo = HMCBackedFIFO(width=len(outfifo_in), start_addr=pe_id*(1<<20), end_addr=(pe_id + 1)*(1<<20), port=config.platform.getHMCPort(pe_id))
        # self.submodules.outfifo = RecordFIFOBuffered(layout=, depth=len(config.adj_idx[pe_id])*2)
        self.comb += [
            self.outfifo.din.eq(outfifo_in.raw_bits()),
            outfifo_out.raw_bits().eq(self.outfifo.dout)
        ]


        # stall if fifo full or if collision
        self.comb += downstream_ack.eq(self.outfifo.writable)

        self.comb += [
            self.outfifo.we.eq(self.applykernel.update_valid | self.applykernel.barrier_out),
            outfifo_in.msg.eq(self.applykernel.update_out.raw_bits()),
            If(self.applykernel.barrier_out, outfifo_in.sender.eq(pe_id << log2_int(num_nodes_per_pe))
            ).Else(outfifo_in.sender.eq(self.applykernel.update_sender)),
            outfifo_in.roundpar.eq(self.applykernel.update_round),
            outfifo_in.barrier.eq(self.applykernel.barrier_out)
        ]

        payload4 = Signal(addresslayout.payloadsize)
        sender4 = Signal(addresslayout.nodeidsize)
        roundpar4 = Signal(config.addresslayout.channel_bits)
        barrier4 = Signal()
        valid4 = Signal()

        self.sync += If(self.scatter_interface.ack,
            payload4.eq(outfifo_out.msg),
            sender4.eq(outfifo_out.sender),
            roundpar4.eq(outfifo_out.roundpar),
            barrier4.eq(outfifo_out.barrier),
            valid4.eq(self.outfifo.readable)
        )

        self.comb += [
            self.scatter_interface.payload.eq(payload4),
            self.scatter_interface.sender.eq(sender4),
            self.scatter_interface.roundpar.eq(roundpar4),
            self.scatter_interface.barrier.eq(barrier4),
            self.scatter_interface.valid.eq(valid4)
        ]

        # send from fifo when receiver ready
        self.comb += self.outfifo.re.eq(self.scatter_interface.ack)
