from migen import *
from tbsupport import *
from migen.genlib.fifo import SyncFIFO, _inc

from util.pico import *

from util.mem import FullyInitMemory

class HMCBackedFIFO(Module):
    def __init__(self, width, start_addr, end_addr, port):
        self.submodules.port = HMCPortWriteUnifier(port)
        assert width <= len(self.port.rd_data)
        print("Using memory region {:x} to {:x}".format(start_addr, end_addr))

        self.din = Signal(width)
        self.writable = Signal()
        self.we = Signal()

        self.dout = Signal(width)
        self.readable = Signal()
        self.re = Signal()

        self.full = Signal()
        self.num_writes = Signal(32)
        self.num_reads = Signal(32)
        self.max_level = Signal(32)

        word_offset = log2_int(len(self.port.rd_data)) - 3

        # storage area
        word_start_addr = start_addr >> word_offset
        word_end_addr = end_addr >> word_offset
        mem_area_size = word_end_addr - word_start_addr
        rd_ptr = Signal(len(self.port.addr)-word_offset)
        wr_ptr = Signal(len(self.port.addr)-word_offset)
        level = Signal(max=mem_area_size+1)

        self.comb += [
            self.full.eq(level == mem_area_size)
        ]
        self.sync += [
            If(self.writable & self.we,
                self.num_writes.eq(self.num_writes + 1)
            ),
            If(self.readable & self.re,
                self.num_reads.eq(self.num_reads + 1)
            ),
            If(level > self.max_level,
                self.max_level.eq(level)
            )
        ]

        # tags
        tag_sz = self.port.effective_max_tag_size - 1
        num_tags = min(2**tag_sz, mem_area_size)
        self.tag_in_use = Array(Signal() for _ in range(num_tags))
        tag = Signal(self.port.effective_max_tag_size - 1)
        self.comb += tag.eq(self.port.addr[word_offset:word_offset+tag_sz])

        # reorder buffer for returned results
        self.specials.reorder_buffer = FullyInitMemory(width, num_tags)
        self.specials.wr_port = wr_port = self.reorder_buffer.get_port(write_capable=True, mode=READ_FIRST)
        self.specials.rd_port = rd_port = self.reorder_buffer.get_port(async_read=True, mode=READ_FIRST)
        reorderbuffer_valid = Array(Signal() for _ in range(num_tags))
        reorder_rd_ptr = Signal(len(rd_port.adr))

        # enforce ordering of accesses to same memory address
        no_hazard = Signal()
        self.comb += no_hazard.eq(~self.tag_in_use[tag])

        # choose read or write; only one port so no simultaneous access
        do_rd = Signal()
        self.sync += do_rd.eq(~do_rd & (level > 0) & ~reorderbuffer_valid[rd_ptr[word_offset:word_offset+tag_sz]] & ~self.tag_in_use[rd_ptr[word_offset:word_offset+tag_sz]]) # read if (a) there is something to read (b) the place to store the return value is free and (c) not going to be filled by an in-flight read

        # issue commands
        self.comb += [
            If(do_rd,
                self.port.cmd.eq(port.HMC_CMD_RD),
                self.port.addr[word_offset:].eq(word_start_addr + rd_ptr),
                self.port.cmd_valid.eq(no_hazard),
                self.writable.eq(0)
            ).Elif(~self.full,
                self.port.cmd.eq(port.HMC_CMD_WR_NP),
                self.port.addr[word_offset:].eq(word_start_addr + wr_ptr),
                self.port.cmd_valid.eq(self.we & no_hazard),
                self.writable.eq(no_hazard & self.port.cmd_ready)
            ).Else(
                self.port.cmd_valid.eq(0),
                self.writable.eq(0)
            ),
            self.port.tag.eq(Cat(do_rd, tag)),
            self.port.wr_data.eq(self.din),
            self.port.size.eq(1)
        ]

        # accounting
        self.sync += [
            If(self.port.cmd_ready & self.port.cmd_valid,
                self.tag_in_use[tag].eq(1),
                If(self.port.cmd == port.HMC_CMD_RD,
                    _inc(rd_ptr, mem_area_size),
                    level.eq(level-1)
                ).Else(
                    _inc(wr_ptr, mem_area_size),
                    level.eq(level+1)
                )
            ),
            If(self.port.rd_data_valid,
                self.tag_in_use[self.port.rd_data_tag[1:]].eq(0),
                If(self.port.rd_data_tag[0],
                    reorderbuffer_valid[self.port.rd_data_tag[1:]].eq(1)
                )
            ),
            If(self.readable & self.re,
                _inc(reorder_rd_ptr, num_tags),
                reorderbuffer_valid[reorder_rd_ptr].eq(0)
            )
        ]

        # fill reorder buffer
        self.comb += [
            self.wr_port.adr.eq(self.port.rd_data_tag[1:]),
            self.wr_port.dat_w.eq(self.port.rd_data),
            self.wr_port.we.eq(self.port.rd_data_valid & self.port.rd_data_tag[0])
        ]

        # read from reorder buffer
        self.comb += [
            self.rd_port.adr.eq(reorder_rd_ptr),
            self.dout.eq(self.rd_port.dat_r),
            self.readable.eq(reorderbuffer_valid[reorder_rd_ptr])
        ]
