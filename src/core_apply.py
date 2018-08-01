from migen import *
from migen.genlib.record import *
from migen.genlib.fifo import SyncFIFO
from recordfifo import InterfaceFIFO
from tbsupport import *

from core_interfaces import ApplyInterface, ScatterInterface, Message
from core_collision import CollisionDetector
from hmc_backed_fifo import HMCBackedFIFO

import logging

class Apply(Module):
    def __init__(self, config, pe_id):
        self.config = config
        self.pe_id = pe_id
        addresslayout = config.addresslayout
        nodeidsize = addresslayout.nodeidsize
        num_nodes_per_pe = addresslayout.num_nodes_per_pe

        # input Q interface
        self.apply_interface = ApplyInterface(name="apply_in", **addresslayout.get_params())

        # scatter interface
        # send self.update message to all neighbors
        # message format (sending_node_id) (normally would be (sending_node_id, weight), but for PR weight = sending_node_id)
        self.scatter_interface = ScatterInterface(name="apply_out", **addresslayout.get_params())

        self.deadlock = Signal()

        ####

        apply_interface_in_fifo = InterfaceFIFO(layout=self.apply_interface.layout, depth=8, name="apply_in_fifo")
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
            barrier.eq(apply_interface_in_fifo.dout.valid & apply_interface_in_fifo.dout.msg.barrier & ~apply_interface_in_fifo.dout.msg.halt),
        ]

        ## Stage 2
        dest_node_id2 = Signal(nodeidsize)
        sender2 = Signal(nodeidsize)
        payload2 = Signal(addresslayout.payloadsize)
        roundpar2 = Signal(config.addresslayout.channel_bits)
        barrier2 = Signal()
        valid2 = Signal()
        ready = Signal()
        msgvalid2 = Signal()
        statevalid2 = Signal()

        state_barrier = Signal()

        node_idx = Signal(nodeidsize)
        gather_done = Signal()

        next_roundpar = Signal(config.addresslayout.channel_bits)
        self.comb += If(roundpar==config.addresslayout.num_channels-1, next_roundpar.eq(0)).Else(next_roundpar.eq(roundpar+1))

        self.submodules.fsm = FSM()
        self.fsm.act("GATHER",
            rd_port.re.eq(upstream_ack),
            apply_interface_in_fifo.dout.ack.eq(upstream_ack),
            rd_port.adr.eq(addresslayout.local_adr(dest_node_id)),
            NextValue(collision_en, 1),
            If(~collision_re,
                NextValue(valid2, 0) # insert bubble if collision
            ).Elif(upstream_ack,
                NextValue(valid2, valid),
                NextValue(dest_node_id2, dest_node_id),
                NextValue(sender2, sender),
                NextValue(payload2, payload),
                NextValue(roundpar2, next_roundpar),
                NextValue(statevalid2, 1),
                NextValue(msgvalid2, ~barrier),
                If(barrier,
                    NextValue(collision_en, 0),
                    NextValue(valid2, 0),
                    NextState("FLUSH")
                )
            )
        )
        self.fsm.act("FLUSH",
            rd_port.re.eq(0),
            NextValue(node_idx, pe_id << log2_int(num_nodes_per_pe)),
            apply_interface_in_fifo.dout.ack.eq(0),
            rd_port.adr.eq(addresslayout.local_adr(dest_node_id)),
            If(gather_done,
                NextState("APPLY")
            )
        )
        self.fsm.act("APPLY",
            rd_port.re.eq(ready),
            apply_interface_in_fifo.dout.ack.eq(0),
            rd_port.adr.eq(addresslayout.local_adr(node_idx)),
            If(ready,
                NextValue(valid2, 1),
                NextValue(dest_node_id2, node_idx),
                NextValue(node_idx, node_idx+1),
                If(node_idx==(len(config.adj_idx[pe_id]) + (pe_id << log2_int(num_nodes_per_pe))),
                    NextValue(statevalid2, 0),
                    NextValue(barrier2, 1),
                    NextValue(valid2, 1),
                    NextState("BARRIER_SEND")
                )
            )
        )
        self.fsm.act("BARRIER_SEND",
            apply_interface_in_fifo.dout.ack.eq(0),
            rd_port.adr.eq(addresslayout.local_adr(node_idx)),
            If(ready,
                NextValue(barrier2, 0),
                NextValue(valid2, 0),
                If(state_barrier,
                    NextValue(self.level, self.level+1),
                    NextState("GATHER")
                ).Else(
                    NextState("BARRIER_WAIT")
                )
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
            self.collisiondetector.read_adr_valid.eq(ready & valid & collision_en), # can't be rd_port.re because that uses collisiondetector.re -> comb loop
            self.collisiondetector.write_adr.eq(local_wr_port.adr),
            self.collisiondetector.write_adr_valid.eq(local_wr_port.we),
            collision_re.eq(self.collisiondetector.re),
            gather_done.eq(self.collisiondetector.all_clear)
        ]

        # User code
        self.submodules.gatherapplykernel = config.gatherapplykernel(config)

        self.comb += [
            self.gatherapplykernel.level_in.eq(self.level),
            self.gatherapplykernel.nodeid_in.eq(dest_node_id2),
            self.gatherapplykernel.sender_in.eq(sender2),
            self.gatherapplykernel.message_in.raw_bits().eq(payload2),
            self.gatherapplykernel.message_in_valid.eq(msgvalid2),
            self.gatherapplykernel.state_in.raw_bits().eq(rd_port.dat_r),
            self.gatherapplykernel.state_in_valid.eq(statevalid2),
            self.gatherapplykernel.round_in.eq(roundpar2),
            self.gatherapplykernel.barrier_in.eq(barrier2),
            self.gatherapplykernel.valid_in.eq(valid2),
            ready.eq(self.gatherapplykernel.ready),
            upstream_ack.eq((self.gatherapplykernel.ready | ~valid2) & collision_re)
        ]

        # write state updates
        self.comb += [
            local_wr_port.adr.eq(addresslayout.local_adr(self.gatherapplykernel.nodeid_out)),
            local_wr_port.dat_w.eq(self.gatherapplykernel.state_out.raw_bits()),
            state_barrier.eq(self.gatherapplykernel.state_barrier),
            local_wr_port.we.eq(self.gatherapplykernel.state_valid),
            self.gatherapplykernel.state_ack.eq(1)
        ]

        # output handling
        _layout = [
        ( "barrier", 1, DIR_M_TO_S ),
        ( "roundpar", config.addresslayout.channel_bits, DIR_M_TO_S ),
        ( "sender", "nodeidsize", DIR_M_TO_S ),
        ( "msg" , addresslayout.payloadsize, DIR_M_TO_S )
        ]
        outfifo_in = Record(set_layout_parameters(_layout, **addresslayout.get_params()))
        outfifo_out = Record(set_layout_parameters(_layout, **addresslayout.get_params()))
        
        self.submodules.outfifo = HMCBackedFIFO(width=len(outfifo_in), start_addr=pe_id*(1<<config.hmc_fifo_bits), end_addr=(pe_id + 1)*(1<<config.hmc_fifo_bits), port=config.platform.getHMCPort(pe_id))
        
        self.sync += [
            If(self.outfifo.full, self.deadlock.eq(1))
        ]

        self.comb += [
            self.outfifo.din.eq(outfifo_in.raw_bits()),
            outfifo_out.raw_bits().eq(self.outfifo.dout)
        ]

        self.comb += [
            outfifo_in.msg.eq(self.gatherapplykernel.update_out.raw_bits()),
            If(self.gatherapplykernel.barrier_out, outfifo_in.sender.eq(pe_id << log2_int(num_nodes_per_pe))
            ).Else(outfifo_in.sender.eq(self.gatherapplykernel.update_sender)),
            self.outfifo.we.eq(self.gatherapplykernel.update_valid),
            outfifo_in.roundpar.eq(self.gatherapplykernel.update_round),
            outfifo_in.barrier.eq(self.gatherapplykernel.barrier_out),
            self.gatherapplykernel.update_ack.eq(self.outfifo.writable)
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

    def gen_simulation(self, tb):
        logger = logging.getLogger('sim.apply')
        while not (yield tb.global_inactive):
            yield
        if self.pe_id == 0:
            print("State at end of computation:")
        for node in range(len(tb.config.adj_idx[self.pe_id])):
            p = str(tb.config.addresslayout.global_adr(self.pe_id, node))
            p += ": "
            state = convert_int_to_record((yield self.mem[node]), tb.config.addresslayout.node_storage_layout)
            p += str(state)
            logger.info(p)
