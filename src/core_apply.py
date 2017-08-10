from migen import *
from migen.genlib.record import *
from recordfifo import *

from core_interfaces import ApplyInterface, ScatterInterface, Message
from core_collision import CollisionDetector



## for wrapping signals when multiplexing memory port
_memory_port_layout = [
    ( "enable", 1 ),
    ( "adr", "adrsize" ),
    ( "re", 1 ),
    ( "dat_r", "datasize" )
]

class Apply(Module):
    def __init__(self, config, pe_id, init_nodedata=None):
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

        apply_interface_in_fifo = InterfaceFIFO(layout=self.apply_interface.layout, depth=2)
        self.submodules += apply_interface_in_fifo
        self.comb += self.apply_interface.connect(apply_interface_in_fifo.din)

        # local node data storage
        if init_nodedata == None:
            init_nodedata = [0 for i in range(num_nodes_per_pe)]
        self.specials.mem = Memory(layout_len(addresslayout.node_storage_layout), max(2, len(init_nodedata)), init=init_nodedata, name="vertex_data_{}".format(self.pe_id))
        rd_port = self.specials.rd_port = self.mem.get_port(has_re=True)
        wr_port = self.specials.wr_port = self.mem.get_port(write_capable=True)

        # multiplex read port
        # TODO: during computation, update locally; after computation, controller sends contents back to host
        # self.extern_rd_port = Record(set_layout_parameters(_memory_port_layout, adrsize=len(rd_port.adr), datasize=len(rd_port.dat_r)))
        local_rd_port = Record(set_layout_parameters(_memory_port_layout, adrsize=len(rd_port.adr), datasize=len(rd_port.dat_r)))
        self.comb += [
            # If(self.extern_rd_port.enable,
            #     rd_port.adr.eq(self.extern_rd_port.adr),
            #     rd_port.re.eq(self.extern_rd_port.re)
            # ).Else(
            rd_port.adr.eq(local_rd_port.adr),
            rd_port.re.eq(local_rd_port.re),
            # ),
            # self.extern_rd_port.dat_r.eq(rd_port.dat_r),
            local_rd_port.dat_r.eq(rd_port.dat_r)
        ]

        # detect termination (now done by collating votes to halt in barriercounter - if barrier is passed on with halt bit set, don't propagate)
        self.inactive = Signal()
        prev_was_barrier = Signal()
        prev_prev_was_barrier = Signal()
        self.sync += \
            If(apply_interface_in_fifo.dout.valid & apply_interface_in_fifo.dout.ack,
                prev_was_barrier.eq(apply_interface_in_fifo.dout.msg.barrier),
                prev_prev_was_barrier.eq(prev_was_barrier)
            )
        self.comb += self.inactive.eq(prev_was_barrier & prev_prev_was_barrier)
        # self.sync += If(apply_interface_in_fifo.dout.valid & apply_interface_in_fifo.dout.ack & apply_interface_in_fifo.dout.msg.barrier & apply_interface_in_fifo.dout.msg.halt,
        #     self.inactive.eq(1)
        # )

        # should pipeline advance?
        upstream_ack = Signal()
        collision_re = Signal()

        # count levels
        self.level = Signal(32)

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
            barrier.eq(apply_interface_in_fifo.dout.valid & apply_interface_in_fifo.dout.msg.barrier), # & ~apply_interface_in_fifo.dout.msg.halt),
        ]

        # collision handling (combinatorial)
        self.submodules.collisiondetector = CollisionDetector(addresslayout)

        self.comb += self.collisiondetector.read_adr.eq(addresslayout.local_adr(dest_node_id)),\
                     self.collisiondetector.read_adr_valid.eq(valid),\
                     self.collisiondetector.write_adr.eq(wr_port.adr),\
                     self.collisiondetector.write_adr_valid.eq(wr_port.we),\
                     collision_re.eq(self.collisiondetector.re)

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

        num_nodes_in_use = Signal(nodeidsize)
        num_nodes_in_use_up = Signal(nodeidsize)
        node_idx = Signal(nodeidsize)
        gather_en = Signal()
        collision_en = Signal()

        next_roundpar = Signal(config.addresslayout.channel_bits)
        self.comb += If(roundpar==config.addresslayout.num_channels-1, next_roundpar.eq(0)).Else(next_roundpar.eq(roundpar+1))

        self.submodules.fsm = FSM()
        self.fsm.act("GATHER",
            local_rd_port.re.eq(upstream_ack),
            apply_interface_in_fifo.dout.ack.eq(upstream_ack),
            local_rd_port.adr.eq(addresslayout.local_adr(dest_node_id)),
            NextValue(valid2, valid & collision_re), # insert bubble if collision
            NextValue(num_nodes_in_use, num_nodes_in_use_up + (valid & collision_re)),
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
            local_rd_port.re.eq(upstream_ack),
            NextValue(num_nodes_in_use, num_nodes_in_use_up),
            NextValue(node_idx, pe_id << log2_int(num_nodes_per_pe)),
            apply_interface_in_fifo.dout.ack.eq(0),
            local_rd_port.adr.eq(addresslayout.local_adr(dest_node_id)),
            If(num_nodes_in_use == 0,
                NextState("APPLY")
            ),
            gather_en.eq(1)
        )
        self.fsm.act("APPLY",
            local_rd_port.re.eq(apply_ready),
            apply_interface_in_fifo.dout.ack.eq(0),
            local_rd_port.adr.eq(addresslayout.local_adr(node_idx)),
            NextValue(apply_valid2, 1),
            If(apply_ready,
                NextValue(dest_node_id2, node_idx),
                NextValue(node_idx, node_idx+1),
                If(node_idx==(len(init_nodedata) + (pe_id << log2_int(num_nodes_per_pe))),
                    NextValue(apply_barrier2, 1),
                    NextValue(apply_valid2, 0),
                    NextState("BARRIER_SEND")
                )
            )
        )
        self.fsm.act("BARRIER_SEND",
            apply_interface_in_fifo.dout.ack.eq(0),
            local_rd_port.adr.eq(addresslayout.local_adr(node_idx)),
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

        # collision handling

        self.submodules.collisiondetector = CollisionDetector(addresslayout)

        self.comb += self.collisiondetector.read_adr.eq(addresslayout.local_adr(dest_node_id)),\
                     self.collisiondetector.read_adr_valid.eq(valid & collision_en),\
                     self.collisiondetector.write_adr.eq(wr_port.adr),\
                     self.collisiondetector.write_adr_valid.eq(wr_port.we),\
                     collision_re.eq(self.collisiondetector.re)

        ## Stage 3
        dest_node_id3 = Signal(nodeidsize)
        sender3 = Signal(nodeidsize)
        payload3 = Signal(addresslayout.payloadsize)
        self.roundpar = Signal(config.addresslayout.channel_bits)
        valid3 = Signal()
        data3 = Signal(len(rd_port.dat_r))

        self.submodules.applykernel = config.applykernel(config.addresslayout)
        state_in = Record(addresslayout.node_storage_layout)

        self.sync += [
            If(ready,
                valid3.eq(valid2),
                dest_node_id3.eq(dest_node_id2),
                sender3.eq(sender2),
                payload3.eq(payload2),
                self.roundpar.eq(roundpar2),
                data3.eq(local_rd_port.dat_r)
            ),
            If(apply_ready,
                self.applykernel.nodeid_in.eq(dest_node_id2),
                self.applykernel.state_in.raw_bits().eq(local_rd_port.dat_r),
                self.applykernel.round_in.eq(roundpar2),
                self.applykernel.valid_in.eq(state_in.active & apply_valid2),
                self.applykernel.barrier_in.eq(apply_barrier2),
            )
        ]

        downstream_ack = Signal()

        self.comb += [
            state_in.raw_bits().eq(local_rd_port.dat_r),
            apply_ready.eq(self.applykernel.ready),
            self.applykernel.update_ack.eq(downstream_ack),
            state_barrier.eq(self.applykernel.state_barrier)
        ]

        # User code
        self.submodules.gatherkernel = config.gatherkernel(config.addresslayout)

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
            wr_port.adr.eq(addresslayout.local_adr(self.gatherkernel.nodeid_out)),
            wr_port.dat_w.eq(self.gatherkernel.state_out.raw_bits()),
            wr_port.we.eq(self.gatherkernel.state_valid)
        ).Else(
            wr_port.adr.eq(addresslayout.local_adr(self.applykernel.nodeid_out)),
            wr_port.dat_w.eq(self.applykernel.state_out.raw_bits()),
            wr_port.we.eq(self.applykernel.state_valid)
        )

        self.comb += [
            If((self.gatherkernel.state_valid & self.gatherkernel.state_ack),
                num_nodes_in_use_up.eq(num_nodes_in_use - 1)
            ).Else(
                num_nodes_in_use_up.eq(num_nodes_in_use)
            )
        ]

        # output handling
        _layout = [
        ( "barrier", 1, DIR_M_TO_S ),
        ( "roundpar", config.addresslayout.channel_bits, DIR_M_TO_S ),
        ( "sender", "nodeidsize", DIR_M_TO_S ),
        ( "msg" , addresslayout.payloadsize, DIR_M_TO_S )
        ]
        self.submodules.outfifo = RecordFIFOBuffered(layout=set_layout_parameters(_layout, **addresslayout.get_params()), depth=4*len(init_nodedata))

        # stall if fifo full or if collision
        self.comb += downstream_ack.eq(self.outfifo.writable)

        self.comb += [
            self.outfifo.we.eq(self.applykernel.update_valid | self.applykernel.barrier_out),
            self.outfifo.din.msg.eq(self.applykernel.update_out.raw_bits()),
            If(self.applykernel.barrier_out, self.outfifo.din.sender.eq(pe_id << log2_int(num_nodes_per_pe))
            ).Else(self.outfifo.din.sender.eq(self.applykernel.update_sender)),
            self.outfifo.din.roundpar.eq(self.applykernel.update_round),
            self.outfifo.din.barrier.eq(self.applykernel.barrier_out)
        ]

        payload4 = Signal(addresslayout.payloadsize)
        sender4 = Signal(addresslayout.nodeidsize)
        roundpar4 = Signal(config.addresslayout.channel_bits)
        barrier4 = Signal()
        valid4 = Signal()

        self.sync += If(self.scatter_interface.ack,
            payload4.eq(self.outfifo.dout.msg),
            sender4.eq(self.outfifo.dout.sender),
            roundpar4.eq(self.outfifo.dout.roundpar),
            barrier4.eq(self.outfifo.dout.barrier),
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
