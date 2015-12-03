from migen import *
from migen.fhdl.specials import READ_FIRST
from migen.genlib.record import *


class CollisionDetector(Module):
    def __init__(self, addresslayout):
        nodeidsize = addresslayout.nodeidsize
        num_nodes_per_pe = addresslayout.num_nodes_per_pe

        self.read_adr = Signal(nodeidsize)
        self.read_adr_valid = Signal()

        self.write_adr = Signal(nodeidsize)
        self.write_adr_valid = Signal()

        self.re = Signal()

        ###

        arraysize = min(32, num_nodes_per_pe)
        
        self.state = Array([Signal(name="hazard_flag") for _ in range(arraysize)])

        self.comb += [
            self.re.eq(~self.state[self.read_adr[:log2_int(arraysize)]] | ~self.read_adr_valid)
        ]

        self.sync += [
            If(self.re & self.read_adr_valid,
                self.state[self.read_adr[:log2_int(arraysize)]].eq(1)
            ),
            If(self.write_adr_valid,
                self.state[self.write_adr[:log2_int(arraysize)]].eq(0)
            )
        ]