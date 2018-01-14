from migen import *
from tbsupport import *
from migen.genlib.record import *
from migen.genlib.roundrobin import *
from migen.genlib.fifo import *

import logging

class DDRPortSharer(Module):

    def __init__(self, config, num_ports, ID_WIDTH=4, ADDR_WIDTH=33, DATA_WIDTH=64*8):
        self.config = config

        _ddr_layout = [
            ("arid", "ID_WIDTH", DIR_M_TO_S),
            ("araddr", "ADDR_WIDTH", DIR_M_TO_S),
            ("arready", 1, DIR_S_TO_M),
            ("arvalid", 1, DIR_M_TO_S),
            ("rid", "ID_WIDTH", DIR_S_TO_M),
            ("rdata", "DATA_WIDTH", DIR_S_TO_M),
            ("rready", 1, DIR_M_TO_S),
            ("rvalid", 1, DIR_S_TO_M)
        ]

        self.real_port = Record(set_layout_parameters(_ddr_layout, ID_WIDTH=ID_WIDTH, ADDR_WIDTH=ADDR_WIDTH, DATA_WIDTH=DATA_WIDTH))
        self.ports = [Record(set_layout_parameters(_ddr_layout, ID_WIDTH=ID_WIDTH, ADDR_WIDTH=ADDR_WIDTH, DATA_WIDTH=DATA_WIDTH)) for _ in range(num_ports)]

        if num_ports == 0:
            return
        if num_ports == 1:
            self.comb += self.ports[0].connect(self.real_port)
            return

        #buffer ports with fifos for better timing

        addr_fifos = [SyncFIFO(width=ADDR_WIDTH, depth=8) for _ in range(num_ports)]
        data_fifos = [SyncFIFO(width=DATA_WIDTH, depth=8) for _ in range(num_ports)]

        self.submodules += addr_fifos
        self.submodules += data_fifos

        for i in range(num_ports):
            self.comb += [
                addr_fifos[i].din.eq(self.ports[i].araddr),
                addr_fifos[i].we.eq(self.ports[i].arvalid),
                self.ports[i].arready.eq(addr_fifos[i].writable),
                self.ports[i].rdata.eq(data_fifos[i].dout),
                self.ports[i].rvalid.eq(data_fifos[i].readable),
                data_fifos[i].re.eq(self.ports[i].rready)
            ]

        # multiplex between ports

        # ensure tag is large enough to number ports
        assert(num_ports <= 2**ID_WIDTH)

        array_arvalid = Array(addr_fifo.readable for addr_fifo in addr_fifos)
        array_arready = Array(addr_fifo.re for addr_fifo in addr_fifos)
        array_araddr = Array(addr_fifo.dout for addr_fifo in addr_fifos)

        self.submodules.roundrobin = RoundRobin(num_ports, switch_policy=SP_CE)

        n_reg_stages = 3
        arid_reg = [Signal(ID_WIDTH) for _ in range(n_reg_stages)]
        araddr_reg = [Signal(ADDR_WIDTH) for _ in range(n_reg_stages)]
        arvalid_reg = [Signal() for _ in range(n_reg_stages)]

        for i in range(1, n_reg_stages):
            self.sync += [
                If(self.real_port.arready,
                    arid_reg[i].eq(arid_reg[i-1]),
                    araddr_reg[i].eq(araddr_reg[i-1]),
                    arvalid_reg[i].eq(arvalid_reg[i-1])
                )
            ]

        self.sync += [
            If(self.real_port.arready,
                self.real_port.arid.eq(arid_reg[-1]),
                self.real_port.araddr.eq(araddr_reg[-1]),
                self.real_port.arvalid.eq(arvalid_reg[-1])
            )
        ]

        self.comb += [
            [self.roundrobin.request[i].eq(port.arvalid) for i, port in enumerate(self.ports)],
            self.roundrobin.ce.eq(self.real_port.arready),
            array_arready[self.roundrobin.grant].eq(self.real_port.arready),
            arvalid_reg[0].eq(array_arvalid[self.roundrobin.grant]),
            araddr_reg[0].eq(array_araddr[self.roundrobin.grant]),
            arid_reg[0].eq(self.roundrobin.grant)
        ]

        array_rvalid = Array(data_fifo.we for data_fifo in data_fifos)
        array_rready = Array(data_fifo.writable for data_fifo in data_fifos)

        data_reg = Signal(DATA_WIDTH)
        id_reg = Signal(ID_WIDTH)
        valid_reg = Signal()

        self.sync += [
            If(self.real_port.rready,
                data_reg.eq(self.real_port.rdata),
                id_reg.eq(self.real_port.rid),
                valid_reg.eq(self.real_port.rvalid)
            )
        ]

        self.comb += [
            [data_fifo.din.eq(data_reg) for data_fifo in data_fifos],
            array_rvalid[id_reg].eq(valid_reg),
            self.real_port.rready.eq(array_rready[id_reg] | ~valid_reg)
        ]

    def get_port(self, i):
        return self.ports[i]

    def get_ios(self):
        return set(self.real_port.flatten())

    @passive
    def gen_simulation(self, tb):
        logger = logging.getLogger("ddr_sim")
        edges_per_burst = len(self.real_port.rdata)//32
        burst_bytes = len(self.real_port.rdata)//8
        inflight_requests = []
        yield self.real_port.arready.eq(1)
        yield self.real_port.rvalid.eq(0)
        while True:
            if (yield self.real_port.rready):
                if inflight_requests: # and random.choice([True, False])
                    tag, addr = inflight_requests[0]
                    inflight_requests.pop(0)
                    logger.debug("Request: addr = {}, tag = {}".format(hex(addr), tag))
                    assert(addr % burst_bytes == 0)
                    idx = addr // 4
                    data = 0
                    for i in reversed(range(edges_per_burst)):
                        data = (data << 32) | self.config.adj_val[idx + i]
                    yield self.real_port.rdata.eq(data)
                    yield self.real_port.rid.eq(tag)
                    yield self.real_port.rvalid.eq(1)
                else:
                    yield self.real_port.rvalid.eq(0)
            yield
            if (yield self.real_port.arready) and (yield self.real_port.arvalid):
                inflight_requests.append(((yield self.real_port.arid), (yield self.real_port.araddr)))
