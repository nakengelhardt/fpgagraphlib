from migen import *
from migen.genlib.record import *
from migen.genlib.fifo import *
from recordfifo import *
from tbsupport import *

from collections import Iterable
import logging
logger = logging.getLogger("axisim")

# // APPLICATION DOMAIN CLOCK AND RESET SIGNAL DROVE BY AND SYNCHRONISED FROM MEMORY DOMAIN
# //
# wire                                                    app_axi_aclk;
# wire                                                    app_axi_aresetn;
#
# // AXI4 MEMORY MAPPED INTERFACE
# //
# // WRITE ADDRESS PORTS
# //
# (* keep = "true" *)
# wire [AXI_ID_WIDTH       - 1 : 0]                       app_axi_awid[NUM_MEM_CTRL - 1 : 0];
# (* keep = "true" *)
# wire [AXI_ADDR_WIDTH     - 1 : 0]                       app_axi_awaddr[NUM_MEM_CTRL - 1 : 0];
# (* keep = "true" *)
# wire [AXI_LEN_WIDTH      - 1 : 0]                       app_axi_awlen[NUM_MEM_CTRL - 1 : 0];
# (* keep = "true" *)
# wire [AXI_SIZE_WIDTH     - 1 : 0]                       app_axi_awsize[NUM_MEM_CTRL - 1 : 0];
# wire [AXI_BURST_WIDTH    - 1 : 0]                       app_axi_awburst[NUM_MEM_CTRL - 1 : 0];
# wire [AXI_LOCK_WIDTH     - 1 : 0]                       app_axi_awlock[NUM_MEM_CTRL - 1 : 0];
# wire [AXI_CACHE_WIDTH    - 1 : 0]                       app_axi_awcache[NUM_MEM_CTRL - 1 : 0];
# wire [AXI_PROT_WIDTH     - 1 : 0]                       app_axi_awprot[NUM_MEM_CTRL - 1 : 0];
# wire [AXI_QOS_WIDTH      - 1 : 0]                       app_axi_awqos[NUM_MEM_CTRL - 1 : 0];
# wire                                                    app_axi_awready[NUM_MEM_CTRL - 1 : 0];
# wire                                                    app_axi_awvalid[NUM_MEM_CTRL - 1 : 0];
#
# // WRITE DATA PORTS
# //
# // READ/WRITE DATA CHANNEL ID SIDEBAND IS NOT USED IN AXI4 PROTOCOL, READ DATA CHANNEL
# //  ID SIDEBAND IS REQUIRED THOUGH BY THE IP CORE INTERFACE.
# //
# (* keep = "true" *)
# wire [AXI_DATA_WIDTH * 8 - 1 : 0]                       app_axi_wdata[NUM_MEM_CTRL - 1 : 0];
# (* keep = "true" *)
# wire [AXI_DATA_WIDTH     - 1 : 0]                       app_axi_wstrb[NUM_MEM_CTRL - 1 : 0];
# (* keep = "true" *)
# wire                                                    app_axi_wlast[NUM_MEM_CTRL - 1 : 0];
# (* keep = "true" *)
# wire                                                    app_axi_wready[NUM_MEM_CTRL - 1 : 0];
# (* keep = "true" *)
# wire                                                    app_axi_wvalid[NUM_MEM_CTRL - 1 : 0];
#
# // WRITE RESPONSE PORTS
# //
# wire [AXI_ID_WIDTH       - 1 : 0]                       app_axi_bid[NUM_MEM_CTRL - 1 : 0];
# (* keep = "true" *)
# wire [AXI_RESP_WIDTH     - 1 : 0]                       app_axi_bresp[NUM_MEM_CTRL - 1 : 0];
# wire                                                    app_axi_bready[NUM_MEM_CTRL - 1 : 0];
# wire                                                    app_axi_bvalid[NUM_MEM_CTRL - 1 : 0];
#
# // READ ADDRESS PORTS
# //
# (* keep = "true" *)
# wire [AXI_ID_WIDTH       - 1 : 0]                       app_axi_arid[NUM_MEM_CTRL - 1 : 0];
# (* keep = "true" *)
# wire [AXI_ADDR_WIDTH     - 1 : 0]                       app_axi_araddr[NUM_MEM_CTRL - 1 : 0];
# (* keep = "true" *)
# wire [AXI_LEN_WIDTH      - 1 : 0]                       app_axi_arlen[NUM_MEM_CTRL - 1 : 0];
# (* keep = "true" *)
# wire [AXI_SIZE_WIDTH     - 1 : 0]                       app_axi_arsize[NUM_MEM_CTRL - 1 : 0];
# wire [AXI_BURST_WIDTH    - 1 : 0]                       app_axi_arburst[NUM_MEM_CTRL - 1 : 0];
# wire [AXI_LOCK_WIDTH     - 1 : 0]                       app_axi_arlock[NUM_MEM_CTRL - 1 : 0];
# wire [AXI_CACHE_WIDTH    - 1 : 0]                       app_axi_arcache[NUM_MEM_CTRL - 1 : 0];
# wire [AXI_PROT_WIDTH     - 1 : 0]                       app_axi_arprot[NUM_MEM_CTRL - 1 : 0];
# wire [AXI_QOS_WIDTH      - 1 : 0]                       app_axi_arqos[NUM_MEM_CTRL - 1 : 0];
# wire                                                    app_axi_arready[NUM_MEM_CTRL - 1 : 0];
# wire                                                    app_axi_arvalid[NUM_MEM_CTRL - 1 : 0];
#
# // READ DATA PORTS
# //
# wire [AXI_ID_WIDTH       - 1 : 0]                       app_axi_rid[NUM_MEM_CTRL - 1 : 0];
# (* keep = "true" *)
# wire [AXI_DATA_WIDTH * 8 - 1 : 0]                       app_axi_rdata[NUM_MEM_CTRL - 1 : 0];
# (* keep = "true" *)
# wire [AXI_RESP_WIDTH     - 1 : 0]                       app_axi_rresp[NUM_MEM_CTRL - 1 : 0];
# (* keep = "true" *)
# wire                                                    app_axi_rlast[NUM_MEM_CTRL - 1 : 0];
# wire                                                    app_axi_rready[NUM_MEM_CTRL - 1 : 0];
# wire                                                    app_axi_rvalid[NUM_MEM_CTRL - 1 : 0];

_axi_layout = [
    ("aw", [
        ("id", "AXI_ID_WIDTH", DIR_M_TO_S),
        ("addr", "AXI_ADDR_WIDTH", DIR_M_TO_S),
        ("len", "AXI_LEN_WIDTH", DIR_M_TO_S),
        ("size", "AXI_SIZE_WIDTH", DIR_M_TO_S),
        ("burst", "AXI_BURST_WIDTH", DIR_M_TO_S),
        ("lock", "AXI_LOCK_WIDTH", DIR_M_TO_S),
        ("cache", "AXI_CACHE_WIDTH", DIR_M_TO_S),
        ("prot", "AXI_PROT_WIDTH", DIR_M_TO_S),
        ("qos", "AXI_QOS_WIDTH", DIR_M_TO_S),
        ("ready", 1, DIR_S_TO_M),
        ("valid", 1, DIR_M_TO_S)
    ]),

    ("w", [
        ("data", "AXI_DATA_WIDTHx8", DIR_M_TO_S),
        ("strb", "AXI_DATA_WIDTH", DIR_M_TO_S),
        ("last", 1, DIR_M_TO_S),
        ("ready", 1, DIR_S_TO_M),
        ("valid", 1, DIR_M_TO_S)
    ]),

    ("b", [
        ("id", "AXI_ID_WIDTH", DIR_S_TO_M),
        ("resp", "AXI_RESP_WIDTH", DIR_S_TO_M),
        ("ready", 1, DIR_M_TO_S),
        ("valid", 1, DIR_S_TO_M)
    ]),

    ("ar", [
        ("id", "AXI_ID_WIDTH", DIR_M_TO_S),
        ("addr", "AXI_ADDR_WIDTH", DIR_M_TO_S),
        ("len", "AXI_LEN_WIDTH", DIR_M_TO_S),
        ("size", "AXI_SIZE_WIDTH", DIR_M_TO_S),
        ("burst", "AXI_BURST_WIDTH", DIR_M_TO_S),
        ("lock", "AXI_LOCK_WIDTH", DIR_M_TO_S),
        ("cache", "AXI_CACHE_WIDTH", DIR_M_TO_S),
        ("prot", "AXI_PROT_WIDTH", DIR_M_TO_S),
        ("qos", "AXI_QOS_WIDTH", DIR_M_TO_S),
        ("ready", 1, DIR_S_TO_M),
        ("valid", 1, DIR_M_TO_S)
    ]),

    ("r", [
        ("id", "AXI_ID_WIDTH", DIR_S_TO_M),
        ("data", "AXI_DATA_WIDTHx8", DIR_M_TO_S),
        ("resp", "AXI_RESP_WIDTH", DIR_S_TO_M),
        ("ready", 1, DIR_M_TO_S),
        ("valid", 1, DIR_S_TO_M)
    ])
]

_mem_layout = [
    ("adr", "AXI_ADDR_WIDTH", DIR_M_TO_S),
    ("dat_r", "AXI_DATA_WIDTHx8", DIR_S_TO_M),
    ("dat_w", "AXI_DATA_WIDTHx8", DIR_M_TO_S),
    ("we", 1, DIR_M_TO_S),
    ("en", 1, DIR_M_TO_S)
]

class RequestUnifier(Module):
    def __init__(self, axi_port, mem_port, fifo_depth=8):

        self.submodules.requestfifo = RecordFIFO(layout=[("adr", len(mem_port.adr)), ("we", 1)], depth=fifo_depth)
        self.submodules.writedatafifo = SyncFIFO(width=len(mem_port.dat_w), depth=fifo_depth)
        self.submodules.readdatafifo = RecordFIFO(layout=[("data", len(mem_port.dat_r)), ("id", len(axi_port.r.id))], depth=fifo_depth)

        word_offset = log2_int(len(axi_port.w.strb))

        ## Accept requests (read or write, write has priority)
        # need 1 cycle delay on giving write access to avoid combinatorial path between ready and valid
        grant = Signal()
        self.sync += [
            grant.eq(axi_port.aw.valid)
        ]
        self.comb += [
            If(grant,
                self.requestfifo.din.adr.eq(axi_port.aw.addr),
                self.requestfifo.din.we.eq(1),
                axi_port.aw.ready.eq(self.requestfifo.writable)
            ).Else(
                self.requestfifo.din.adr.eq(axi_port.ar.addr),
                self.requestfifo.din.we.eq(0),
                axi_port.ar.ready.eq(self.requestfifo.writable)
            ),
            self.requestfifo.we.eq((grant & axi_port.aw.valid) | axi_port.ar.valid),
        ]

        ## Accept write data
        self.comb += [
            self.writedatafifo.din.eq(axi_port.w.data),
            self.writedatafifo.we.eq(axi_port.w.valid),
            axi_port.w.ready.eq(self.writedatafifo.writable)
            #FIXME: add wstrb, wlast
        ]

        ## combine requests
        #FIXME: assume length 1 writes (no bursts) for now
        wr_ok = Signal()
        rd_ok = Signal()
        self.comb += [
            mem_port.en.eq(self.requestfifo.readable | self.readdatafifo.we),
            wr_ok.eq(self.requestfifo.dout.we & self.writedatafifo.readable & axi_port.b.ready),
            rd_ok.eq(~self.requestfifo.dout.we & ~self.readdatafifo.almost_full),
            mem_port.adr.eq(self.requestfifo.dout.adr),
            mem_port.we.eq(self.requestfifo.readable & wr_ok),
            mem_port.dat_w.eq(self.writedatafifo.dout),
            self.requestfifo.re.eq((rd_ok | wr_ok)),
            self.readdatafifo.din.data.eq(mem_port.dat_r),
            self.writedatafifo.re.eq(self.requestfifo.readable & wr_ok)
        ]
        self.sync += [
            self.readdatafifo.din.id.eq(axi_port.ar.id),
            self.readdatafifo.we.eq(self.requestfifo.readable & rd_ok),
            axi_port.b.id.eq(axi_port.aw.id),
            axi_port.b.resp.eq(0),
            axi_port.b.valid.eq(self.requestfifo.readable & wr_ok)
        ]

        ## return read data
        self.comb += [
            axi_port.r.id.eq(self.readdatafifo.dout.id),
            axi_port.r.data.eq(self.readdatafifo.dout.data),
            axi_port.r.valid.eq(self.readdatafifo.readable),
            self.readdatafifo.re.eq(axi_port.r.ready)
        ]

class AXIInterface(Record):
    def __init__(self, AXI_ID_WIDTH=4, AXI_ADDR_WIDTH=64, AXI_DATA_WIDTH=64, AXI_LEN_WIDTH=8, AXI_SIZE_WIDTH=3, AXI_BURST_WIDTH=2, AXI_LOCK_WIDTH=1, AXI_CACHE_WIDTH=4, AXI_PROT_WIDTH=3, AXI_QOS_WIDTH=4, AXI_REGION_WIDTH=4, AXI_RESP_WIDTH=2):
        Record.__init__(self, set_layout_parameters(_axi_layout, AXI_ID_WIDTH=AXI_ID_WIDTH, AXI_ADDR_WIDTH=AXI_ADDR_WIDTH, AXI_DATA_WIDTH=AXI_DATA_WIDTH, AXI_DATA_WIDTHx8=AXI_DATA_WIDTH*8, AXI_LEN_WIDTH=AXI_LEN_WIDTH, AXI_SIZE_WIDTH=AXI_SIZE_WIDTH, AXI_BURST_WIDTH=AXI_BURST_WIDTH, AXI_LOCK_WIDTH=AXI_LOCK_WIDTH, AXI_CACHE_WIDTH=AXI_CACHE_WIDTH, AXI_PROT_WIDTH=AXI_PROT_WIDTH, AXI_QOS_WIDTH=AXI_QOS_WIDTH, AXI_REGION_WIDTH=AXI_REGION_WIDTH, AXI_RESP_WIDTH=AXI_RESP_WIDTH))

        self.radrq = []
        self.rdataq = []
        self.wadrq = []
        self.wdataq = []
        self.wrespq = []

    @passive
    def gen_radr(self):
        while True:
            if self.radrq:
                adr, rid, rlen, rsize = self.radrq[0]
                yield self.ar.id.eq(rid)
                yield self.ar.len.eq(rlen)
                yield self.ar.size.eq(rsize)
                yield self.ar.addr.eq(adr)
                yield self.ar.valid.eq(1)
            else:
                yield self.ar.valid.eq(0)
            yield
            if (yield self.ar.valid) and (yield self.ar.ready):
                # logger.debug("read requested @ {}".format(hex(adr)))
                self.radrq.pop(0)

    @passive
    def gen_rdata(self):
        while True:
            yield self.r.ready.eq(1) #TODO: random.choice([0,1])
            yield
            if (yield self.r.ready) and (yield self.r.valid):
                rdata = (yield self.r.data)
                rid = (yield self.r.id)
                resp = (yield self.r.resp)
                # logger.debug("read data {}".format(hex(rdata)))
                self.rdataq.append((rdata, rid, resp))

    def read(self, adr, rid=0, rlen=0, rsize=6):
        logger.debug("read @ {}".format(hex(adr)))
        self.radrq.append((adr, rid, rlen, rsize))
        while not self.rdataq:
            yield
        rdata, rid, resp = self.rdataq.pop(0)
        return rdata

    @passive
    def gen_wadr(self):
        while True:
            if self.wadrq:
                adr, wid, wlen, wsize = self.wadrq[0]
                yield self.aw.id.eq(wid)
                yield self.aw.len.eq(wlen)
                yield self.aw.size.eq(wsize)
                yield self.aw.addr.eq(adr)
                yield self.aw.valid.eq(1)
            else:
                yield self.aw.valid.eq(0)
            yield
            if (yield self.aw.valid) and (yield self.aw.ready):
                # logger.debug("write requested @ {}".format(hex(adr)))
                self.wadrq.pop(0)

    @passive
    def gen_wdata(self):
        while True:
            if self.wdataq:
                wdata, wstrb, wlast = self.wdataq[0]
                yield self.w.data.eq(wdata)
                yield self.w.strb.eq(wstrb)
                yield self.w.last.eq(wlast)
                yield self.w.valid.eq(1)
            else:
                yield self.w.valid.eq(0)
            yield
            if (yield self.w.ready) and (yield self.w.valid):
                # logger.debug("write data {}".format(hex(wdata)))
                self.wdataq.pop(0)

    @passive
    def gen_wresp(self):
        while True:
            yield self.b.ready.eq(1) #TODO: random.choice([0,1])
            yield
            if (yield self.b.ready) and (yield self.b.valid):
                bid = (yield self.b.id)
                resp = (yield self.b.resp)
                self.wrespq.append((bid, resp))

    def write(self, adr, wdata, wid=0, wsize=6, wburst=0b01):
        logger.debug("write {} @ {}".format(hex(wdata), hex(adr)))
        chunks = 2**(len(self.w.strb) - wsize)
        start_offset = adr & (len(self.w.strb) - 1)
        if isinstance(wdata, Iterable):
            for i,d in enumerate(wdata):
                self.wadrq.append((adr, wid, len(wdata)-1, wsize))
                wstrb = ((2**wsize - 1) << ((start_offset + i) % chunks)) % (2**len(self.w.strb))
                wlast = 1 if i == len(wdata)-1 else 0
                da = d << ((start_offset + i) % chunks)*8
                self.wdataq.append((da, wstrb, wlast))
        else:
            self.wadrq.append((adr, wid, 0, wsize))
            # logger.debug("wsize = {}, start_offset = {}, len(wstrb) = {}".format(wsize, start_offset, len(self.w.strb)))
            wstrb = ((2**(2**wsize) - 1) << start_offset) & (2**len(self.w.strb) - 1)
            da = wdata << start_offset*8
            self.wdataq.append((da, wstrb, 1))
        if isinstance(wdata, Iterable):
            for _ in wdata:
                while not self.wrespq:
                    yield
                bid, resp = self.wrespq.pop(0)
        else:
            while not self.wrespq:
                yield
            bid, resp = self.wrespq.pop(0)
        return

class BRAMIO(Module):
    def __init__(self, start_addr, endpoints, AXI_ID_WIDTH=4, AXI_ADDR_WIDTH=64, AXI_DATA_WIDTH=64, AXI_LEN_WIDTH=8, AXI_SIZE_WIDTH=3, AXI_BURST_WIDTH=2, AXI_LOCK_WIDTH=1, AXI_CACHE_WIDTH=4, AXI_PROT_WIDTH=3, AXI_QOS_WIDTH=4, AXI_REGION_WIDTH=4, AXI_RESP_WIDTH=2):
        self.axi_port = axi_port = AXIInterface()
        self.mem_port = mem_port = Record(set_layout_parameters(_mem_layout, AXI_ADDR_WIDTH=AXI_ADDR_WIDTH, AXI_DATA_WIDTHx8=AXI_DATA_WIDTH*8))

        self.submodules.requestunifier = RequestUnifier(axi_port, mem_port)

        self.word_offset = word_offset = log2_int(len(self.axi_port.w.strb))
        self.addr_spacing = addr_spacing = (1 << (max([len(l.adr) for l in endpoints]) + word_offset))
        for l in endpoints:
            if len(l.dat_w) > AXI_DATA_WIDTH*8:
                raise NotImplementedError()
            assert start_addr & (2**len(l.adr) - 1) == 0
            end_addr = start_addr + addr_spacing
            logger.debug("{} assigned to memory region {} - {}".format(l, hex(start_addr), hex(end_addr)))
            select = Signal()
            select_r = Signal()
            self.comb += [
                l.adr.eq(mem_port.adr[word_offset:]),
                l.dat_w.eq(mem_port.dat_w),
                select.eq((mem_port.adr >= start_addr) & (mem_port.adr < end_addr)),
                If(select,
                    l.we.eq(mem_port.we)
                ),
                If(select_r,
                    mem_port.dat_r.eq(l.dat_r)
                )
            ]
            if hasattr(l, "select"):
                self.comb += l.select.eq(mem_port.en)

            self.sync += [
                select_r.eq(select)
            ]

            start_addr = end_addr
