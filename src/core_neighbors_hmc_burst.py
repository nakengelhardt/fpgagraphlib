from migen import *
from migen.genlib.fsm import FSM, NextState, NextValue
from migen.genlib.fifo import SyncFIFO

from util.mem import FullyInitMemory

import logging
import math

_data_layout = [
    ("message", "updatepayloadsize"),
    ("sender", "nodeidsize"),
    ("round", "channel_bits"),
    ("num_neighbors", "edgeidsize"),
    ("nvtx", "nvtx_size")
]

from core_interfaces import _neighbor_in_layout, _neighbor_out_layout

class RequestIssuer(Module):
    def __init__(self, config, hmc_port, updatebuffer):
        # input
        self.neighbor_in = Record(set_layout_parameters(_neighbor_in_layout, **config.addresslayout.get_params()))

        self.tag_in = Signal(hmc_port.effective_max_tag_size)
        self.tag_in_valid = Signal()
        self.tag_in_ack = Signal()

        self.specials.update_wr_port = self.updatebuffer.get_port(write_capable=True, mode=READ_FIRST)
        update_dat_w = Record(set_layout_parameters(_data_layout, **config.addresslayout.get_params()))
        self.comb += [
            self.update_wr_port.dat_w.eq(update_dat_w.raw_bits())
        ]

        # constants
        nodeidsize = config.addresslayout.nodeidsize
        edgeidsize = config.addresslayout.edgeidsize
        if config.has_edgedata:
            edgedatasize = config.addresslayout.edgedatasize
        else:
            edgedatasize = 0

        vertex_size = 2**math.ceil(math.log2(nodeidsize + edgedatasize))
        if vertex_size < 8:
            vertex_size = 8
        vertex_bytes = vertex_size//8
        max_flit_in_burst = 8
        flit_size = len(hmc_port.rd_data)
        vertices_per_flit = flit_size//vertex_size
        vtx_offset = log2_int(vertex_bytes)
        flit_offset = log2_int(flit_size//8)
        burst_offset = flit_offset+log2_int(max_flit_in_burst)

        addr = Signal(edgeidsize)
        end_addr = Signal(edgeidsize)
        length_bytes = Signal(edgeidsize)
        nvtx_remaining = Signal(edgeidsize)

        message = Signal(config.addresslayout.updatepayloadsize)
        sender = Signal(config.addresslayout.nodeidsize)
        roundpar = Signal(config.addresslayout.channel_bits)
        num_neighbors = Signal(edgeidsize)
        valid = Signal()

        get_new_addr = Signal()
        partial_burst = Signal()

        nflit_in_last_burst = Signal(burst_offset-flit_offset)
        nvtx_in_last_flit = Signal(flit_offset-vtx_offset)
        partial_flit = Signal()
        last_cmd = Signal()

        self.comb += [
            nvtx_remaining.eq(length_bytes[vtx_offset:]),
            nflit_in_last_burst.eq(length_bytes[flit_offset:burst_offset] + partial_flit),
            partial_burst.eq(nflit_in_last_burst != 0),
            nvtx_in_last_flit.eq(length_bytes[vtx_offset:flit_offset]),
            partial_flit.eq(nvtx_in_last_flit != 0),
            last_cmd.eq(length_bytes <= max_flit_in_burst*bytes_per_flit)
        ]

        self.sync += [
            If(self.neighbor_in.ack,
                addr.eq(self.neighbor_in.start_idx),
                length_bytes.eq(self.neighbor_in.num_neighbors << vtx_offset),
                end_addr.eq(self.neighbor_in.start_idx + (self.neighbor_in.num_neighbors << vtx_offset)),
                message.eq(self.neighbor_in.message),
                sender.eq(self.neighbor_in.sender),
                roundpar.eq(self.neighbor_in.roundpar),
                num_neighbors.eq(self.neighbor_in.num_neighbors),
                valid.eq(self.neighbor_in.valid)
            ).Elif(self.ordered_port.req.valid & self.ordered_port.req.ack,
                addr.eq(addr + max_flit_in_burst*bytes_per_flit),
            ),
        ]

        self.comb += [
            self.neighbor_in.ack.eq(get_new_addr),
            hmc_port.cmd.eq(hmc_port.HMC_CMD_RD),
            hmc_port.addr.eq(addr),
            If(last_cmd & partial_burst,
                hmc_port.size.eq(nflit_in_last_burst),
            ).Else(
                hmc_port.size.eq(max_flit_in_burst),
            ),
            hmc_port.cmd_valid.eq(valid & self.tag_in_valid),
            self.update_wr_port.adr.eq(current_tag),
            self.update_wr_port.we.eq(hmc_port.cmd_valid),
            update_dat_w.message.eq(message),
            update_dat_w.sender.eq(sender),
            update_dat_w.round.eq(roundpar),
            update_dat_w.num_neighbors.eq(num_neighbors),
            If(partial_burst,
                update_dat_w.nvtx.eq(),
            ).Else(
                update_dat_w.nvtx.eq()
            )


            self.last_fifo.din.eq(last_cmd),
            If(last_cmd & (partial_burst | partial_flit),
                self.length_fifo.din.eq(length_bytes[vtx_offset:burst_offset])
            ).Else(
                self.length_fifo.din.eq(max_flit_in_burst*vertices_per_flit)
            ),

            self.length_fifo.we.eq(self.ordered_port.req.ack & self.ordered_port.req.valid),
            self.last_fifo.we.eq(self.length_fifo.we),
            If(~valid,
                get_new_addr.eq(1),
            ).Elif(hmc_port.cmd_valid & hmc_port.cmd_ready,
                get_new_addr.eq(last_cmd)
            )
        ]



class NeighborsHMC(Module):
    def __init__(self, pe_id, config, edge_data=None, hmc_port=None):
        self.pe_id = pe_id
        nodeidsize = config.addresslayout.nodeidsize
        edgeidsize = config.addresslayout.edgeidsize
        if config.has_edgedata:
            edgedatasize = config.addresslayout.edgedatasize
        else:
            edgedatasize = 0

        # input
        self.neighbor_in = Record(set_layout_parameters(_neighbor_in_layout, **config.addresslayout.get_params()))

        # output
        self.neighbor_out = Record(set_layout_parameters(_neighbor_out_layout, **config.addresslayout.get_params()))

        if not hmc_port:
            hmc_port = config.platform.getHMCPort(pe_id % config.addresslayout.num_pe_per_fpga)

        self.hmc_port = hmc_port
        effective_max_tag_size = self.hmc_port.effective_max_tag_size



        # tag management
        num_injected = Signal(7)
        inject = Signal()
        tag_available = Signal()
        no_tags_inflight = Signal()
        current_tag = Signal(6)
        self.submodules.tags = SyncFIFO(6, 2**effective_max_tag_size)
        self.sync += If(inject & hmc_port.cmd_ready & hmc_port.cmd_valid,
            num_injected.eq(num_injected + 1)
        )
        self.comb += [
            no_tags_inflight.eq(self.tags.level == num_injected),
            inject.eq(num_injected < 2**effective_max_tag_size),
            If(inject,
                current_tag.eq(num_injected),
                tag_available.eq(1)
            ).Else(
                current_tag.eq(self.tags.dout),
                tag_available.eq(self.tags.readable)
            )
        ]

        # buffers
        self.specials.answerbuffer = FullyInitMemory(flit_size, max_flit_in_burst*2**effective_max_tag_size)
        self.specials.answer_rd_port = self.answerbuffer.get_port(async_read=True, mode=READ_FIRST)
        self.specials.answer_wr_port = self.answerbuffer.get_port(write_capable=True, mode=READ_FIRST)
        self.specials.updatebuffer = FullyInitMemory(len(update_dat_w), 2**effective_max_tag_size)
        self.specials.update_rd_port = self.updatebuffer.get_port(async_read=True, mode=READ_FIRST)
