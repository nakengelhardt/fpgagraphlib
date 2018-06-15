from migen import *
from tbsupport import *
from migen.genlib.fifo import SyncFIFO, _inc

from pico import *

class HMCBackedFIFO(Module):
    def __init__(self, width, start_addr, end_addr, port):
        self.port = port
        assert width <= len(self.port.rd_data)
        self.submodules.data = SyncFIFO(width=len(self.port.wr_data), depth=8)

        self.din = self.data.din
        self.writable = Signal()
        self.we = Signal()

        self.dout = Signal(width)
        self.readable = Signal()
        self.re = Signal()

        word_offset = log2_int(len(self.port.rd_data)) - 3

        # storage area
        mem_area_size = (end_addr-start_addr) >> word_offset
        rd_ptr = Signal(len(self.port.addr)-word_offset)
        wr_ptr = Signal(len(self.port.addr)-word_offset)
        level = Signal(max=mem_area_size+1)

        # tags
        tag_sz = self.port.effective_max_tag_size - 1
        num_tags = min(2**tag_sz, mem_area_size)
        self.tag_in_use = Array(Signal() for _ in range(num_tags))
        tag = Signal(self.port.effective_max_tag_size - 1)
        self.comb += tag.eq(self.port.addr[word_offset:word_offset+tag_sz])

        # reorder buffer for returned results
        self.specials.reorder_buffer = Memory(width, num_tags)
        self.specials.wr_port = wr_port = self.reorder_buffer.get_port(write_capable=True, mode=READ_FIRST)
        self.specials.rd_port = rd_port = self.reorder_buffer.get_port(async_read=True, mode=READ_FIRST)
        reorderbuffer_valid = Array(Signal() for _ in range(num_tags))
        reorder_rd_ptr = Signal(len(rd_port.adr))

        # enforce ordering of accesses to same memory address
        no_hazard = Signal()
        self.comb += no_hazard.eq(~self.tag_in_use[tag])

        # choose read or write; only one port so no simultaneous access
        do_rd = Signal()
        self.comb += do_rd.eq((level > 0) & ~reorderbuffer_valid[rd_ptr[word_offset:word_offset+tag_sz]] & ~self.tag_in_use[rd_ptr[word_offset:word_offset+tag_sz]]) # read if (a) there is something to read (b) the place to store the return value is free and (c) not going to be filled by an in-flight read

        # issue commands
        self.comb += [
            If(do_rd,
                self.port.cmd.eq(HMC_CMD_RD),
                self.port.addr[word_offset:].eq(start_addr + rd_ptr),
                self.port.cmd_valid.eq(no_hazard),
                self.writable.eq(0),
                self.data.we.eq(0)
            ).Elif((level != mem_area_size),
                self.port.cmd.eq(HMC_CMD_WR_NP),
                self.port.addr[word_offset:].eq(start_addr + wr_ptr),
                self.port.cmd_valid.eq(self.we & no_hazard),
                self.writable.eq(self.data.writable & no_hazard & self.port.cmd_ready),
                self.data.we.eq(self.we & no_hazard & self.port.cmd_ready)
            ),
            self.port.tag.eq(Cat(do_rd, tag)),
            self.port.wr_data.eq(self.data.dout),
            self.port.wr_data_valid.eq(self.data.readable),
            self.data.re.eq(self.port.wr_data_ready),
            self.port.size.eq(1)
        ]

        # accounting
        self.sync += [
            If(self.port.cmd_ready & self.port.cmd_valid,
                self.tag_in_use[tag].eq(1),
                If(self.port.cmd == HMC_CMD_RD,
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
