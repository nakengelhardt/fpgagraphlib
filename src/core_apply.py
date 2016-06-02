from migen import *
from migen.genlib.record import *
from recordfifo import RecordFIFOBuffered

from core_interfaces import ApplyInterface, ScatterInterface, Message
from core_address import AddressLayout
from core_collision import CollisionDetector



## for wrapping signals when multiplexing memory port
_memory_port_layout = [
    ( "enable", 1 ),
    ( "adr", "adrsize" ),
    ( "re", 1 ),
    ( "dat_r", "datasize" )
]

class Apply(Module):
    def __init__(self, config, init_nodedata=None):
        self.config = config
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

        # should pipeline advance?
        upstream_ack = Signal()

        # local node data storage
        if init_nodedata == None:
            init_nodedata = [0 for i in range(num_nodes_per_pe)]
        self.specials.mem = Memory(addresslayout.node_storage_layout_len, num_nodes_per_pe, init=init_nodedata)
        rd_port = self.specials.rd_port = self.mem.get_port(has_re=True)
        wr_port = self.specials.wr_port = self.mem.get_port(write_capable=True)

        # multiplex read port
        # during computation, update locally; after computation, controller sends contents back to host
        self.extern_rd_port = Record(set_layout_parameters(_memory_port_layout, adrsize=len(rd_port.adr), datasize=len(rd_port.dat_r)))
        local_rd_port = Record(set_layout_parameters(_memory_port_layout, adrsize=len(rd_port.adr), datasize=len(rd_port.dat_r)))
        self.comb += [
            If(self.extern_rd_port.enable,
                rd_port.adr.eq(self.extern_rd_port.adr),
                rd_port.re.eq(self.extern_rd_port.re)
            ).Else(
                rd_port.adr.eq(local_rd_port.adr),
                rd_port.re.eq(local_rd_port.re)
            ),
            self.extern_rd_port.dat_r.eq(rd_port.dat_r),
            local_rd_port.dat_r.eq(rd_port.dat_r)
        ]

        # detect termination (if all PEs receive 2 barriers in a row)
        self.inactive = Signal()
        prev_was_barrier = Signal()
        prev_prev_was_barrier = Signal()
        self.sync += \
            If(self.apply_interface.valid & self.apply_interface.ack,
                prev_was_barrier.eq(self.apply_interface.msg.barrier),
                prev_prev_was_barrier.eq(prev_was_barrier)
            )
        self.comb += self.inactive.eq(prev_was_barrier & prev_prev_was_barrier)

        ## Stage 1
        # rename some signals for easier reading, separate barrier and normal valid (for writing to state mem)
        dest_node_id = Signal(nodeidsize)
        sender = Signal(nodeidsize)
        payload = Signal(addresslayout.payloadsize)
        roundpar = Signal()
        valid = Signal()
        barrier = Signal()

        self.comb += [
            dest_node_id.eq(self.apply_interface.msg.dest_id),
            sender.eq(self.apply_interface.msg.sender),
            payload.eq(self.apply_interface.msg.payload),
            roundpar.eq(self.apply_interface.msg.roundpar),
            valid.eq(self.apply_interface.valid & ~self.apply_interface.msg.barrier),
            barrier.eq(self.apply_interface.valid & self.apply_interface.msg.barrier),
            self.apply_interface.ack.eq(upstream_ack)
        ]

        # collision handling
        collision_re = Signal()
        self.submodules.collisiondetector = CollisionDetector(addresslayout)

        self.comb += self.collisiondetector.read_adr.eq(addresslayout.local_adr(dest_node_id)),\
                     self.collisiondetector.read_adr_valid.eq(valid),\
                     self.collisiondetector.write_adr.eq(wr_port.adr),\
                     self.collisiondetector.write_adr_valid.eq(wr_port.we),\
                     collision_re.eq(self.collisiondetector.re)


        # get node data
        self.comb += local_rd_port.adr.eq(addresslayout.local_adr(dest_node_id)),\
                     local_rd_port.re.eq(upstream_ack)


        ## Stage 2
        dest_node_id2 = Signal(nodeidsize)
        sender2 = Signal(nodeidsize)
        payload2 = Signal(addresslayout.payloadsize)
        roundpar2 = Signal()
        valid2 = Signal()
        barrier2 = Signal()
        data_invalid2 = Signal()
        ready = Signal()

        self.sync += [
            valid2.eq(valid & collision_re), #insert bubble if collision
            barrier2.eq(barrier & collision_re),
            If(upstream_ack,
                dest_node_id2.eq(dest_node_id),
                sender2.eq(sender),
                payload2.eq(payload),
                roundpar2.eq(roundpar)
            )
        ]

        ## Stage 3
        dest_node_id3 = Signal(nodeidsize)
        sender3 = Signal(nodeidsize)
        payload3 = Signal(addresslayout.payloadsize)
        roundpar3 = Signal()
        valid3 = Signal()
        barrier3 = Signal()
        data_invalid3 = Signal()
        data3 = Signal(len(rd_port.dat_r))

        self.sync += [
            If(ready,
                valid3.eq(valid2),
                barrier3.eq(barrier2),
                dest_node_id3.eq(dest_node_id2),
                sender3.eq(sender2),
                payload3.eq(payload2),
                roundpar3.eq(roundpar2),
                data3.eq(local_rd_port.dat_r)
            )
        ]

        # count levels
        self.level = Signal(32)
        self.sync += If(barrier3 & ready, self.level.eq(self.level + 1))

        self.roundpar = roundpar3

        downstream_ack = Signal()

        # User code
        self.submodules.applykernel = config.applykernel(config.addresslayout)

        self.comb += [
            self.applykernel.nodeid_in.eq(dest_node_id3),
            self.applykernel.sender_in.eq(sender3),
            self.applykernel.message_in.raw_bits().eq(payload3),
            self.applykernel.state_in.raw_bits().eq(data3),
            self.applykernel.valid_in.eq(valid3),
            self.applykernel.barrier_in.eq(barrier3),
            self.applykernel.level_in.eq(self.level),
            self.applykernel.update_ack.eq(downstream_ack),
            ready.eq(self.applykernel.ready),
            upstream_ack.eq(self.applykernel.ready & collision_re)
        ]


        # write state updates
        self.comb += [
            wr_port.adr.eq(addresslayout.local_adr(self.applykernel.nodeid_out)),
            wr_port.dat_w.eq(self.applykernel.state_out.raw_bits()),
            wr_port.we.eq(self.applykernel.state_valid)
        ]
        # TODO: reset/init


        # output handling
        _layout = [
        ( "barrier", 1, DIR_M_TO_S ),
        ( "roundpar", 1, DIR_M_TO_S ),
        ( "sender", "nodeidsize", DIR_M_TO_S ),
        ( "msg" , addresslayout.payloadsize, DIR_M_TO_S )
        ]
        self.submodules.outfifo = RecordFIFOBuffered(layout=set_layout_parameters(_layout, **addresslayout.get_params()), depth=2*addresslayout.num_nodes_per_pe)

        # stall if fifo full or if collision
        self.comb += downstream_ack.eq(self.outfifo.writable)

        self.comb += [
            self.outfifo.we.eq(self.applykernel.update_valid | self.applykernel.barrier_out),
            self.outfifo.din.msg.eq(self.applykernel.update_out.raw_bits()),
            self.outfifo.din.sender.eq(self.applykernel.update_sender),
            self.outfifo.din.roundpar.eq(self.applykernel.update_round),
            self.outfifo.din.barrier.eq(self.applykernel.barrier_out)
        ]

        payload4 = Signal(addresslayout.payloadsize)
        sender4 = Signal(addresslayout.nodeidsize)
        roundpar4 = Signal()
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

        # send from fifo when receiver ready and no external request (has priority)
        self.comb += self.outfifo.re.eq(self.scatter_interface.ack & ~self.extern_rd_port.re)

    def gen_stats(self, tb):
        pe_id = tb.apply.index(self)
        num_cycles = 0
        with open("{}.mem_dump.{}pe.{}groups.{}delay.log".format(self.config.name, self.config.addresslayout.num_pe, self.config.addresslayout.pe_groups, self.config.addresslayout.inter_pe_delay), 'w') as memdumpfile:
            memdumpfile.write("Time\tPE\tMemory address\n")
            while not (yield tb.global_inactive):
                num_cycles += 1
                if (yield self.rd_port.re):
                    memdumpfile.write("{}\t{}\t{}\n".format(num_cycles, pe_id, (yield self.rd_port.adr)))
                yield
