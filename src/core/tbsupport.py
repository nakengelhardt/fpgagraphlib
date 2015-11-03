from migen import *
from migen.fhdl import verilog

import struct

class SimCase:
    def setUp(self, *args, **kwargs):
        self.tb = self.TestBench(*args, **kwargs)

    def test_to_verilog(self):
        verilog.convert(self.tb)

    def run_with(self, generators, **kwargs):
        run_simulation(self.tb, generators, **kwargs)

def convert_float_to_32b_int(f):
    return struct.unpack("I", struct.pack("f", f))[0]

def convert_32b_int_to_float(i):
    return struct.unpack("f", struct.pack("I", i))[0]