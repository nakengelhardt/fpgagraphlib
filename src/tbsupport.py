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

def convert_int_to_record(n, record):
    s = bin(n)[2:]
    total_length = sum([field[1] for field in record])
    if len(s) < total_length:
        s = '0'*(total_length-len(s)) + s
    res = {}
    curr_idx = 0
    for field in record[::-1]:
        attr = field[0]
        length = field[1]
        res[attr] = int(s[curr_idx:curr_idx+length], 2)
        curr_idx += length
    return res

def convert_record_to_int(record, **kwargs):
    ret = 0
    for field in record[::-1]:
        ret = (ret << field[1]) | (kwargs[field[0]] if field[0] in kwargs else 0)
    return ret

def ones(bits):
    ret = 0
    for i in range(bits):
        ret = (ret << 1) | 1
    return ret
