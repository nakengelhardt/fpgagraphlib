from migen import *
from migen.fhdl import verilog

import struct
import os
from contextlib import contextmanager
from misc import pack

class SimCase:
    def setUp(self, *args, **kwargs):
        self.tb = self.TestBench(*args, **kwargs)

    def test_to_verilog(self):
        verilog.convert(self.tb)

    def run_with(self, generators, **kwargs):
        run_simulation(self.tb, generators, **kwargs)

def get_simulators(module, name, *args, **kwargs):
    simulators = []
    if hasattr(module, name):
        simulators.append(getattr(module, name)(*args, **kwargs))
    for _, submodule in module._submodules:
            for simulator in get_simulators(submodule, name, *args, **kwargs):
                    simulators.append(simulator)
    return simulators

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
        if field[0] in kwargs:
            assert bits_for(kwargs[field[0]]) <= field[1]
        ret = (ret << field[1]) | (kwargs[field[0]] if field[0] in kwargs else 0)
    return ret

def ones(bits):
    ret = 0
    for i in range(bits):
        ret = (ret << 1) | 1
    return ret

def popcount(val):
    assert val >= 0
    n = 0
    while val:
        n += val & 1
        val >>= 1
    return n

def bit_vector(l):
    bv = 0
    for b in reversed(list(l)):
        bv = (bv << 1) | (1 if b else 0)
    return bv

def get_mem_port_layout(port):
    layout = [
    ("adr", len(port.adr), DIR_M_TO_S),
    ("dat_r", len(port.dat_r), DIR_S_TO_M)
    ]
    if port.re is not None:
        layout.append(("re", len(port.re), DIR_M_TO_S))
    if port.we is not None:
        layout.append(("we", len(port.we), DIR_M_TO_S))
        layout.append(("dat_w", len(port.dat_w), DIR_M_TO_S))
    return layout

@contextmanager
def cd(newdir):
    prevdir = os.getcwd()
    os.chdir(os.path.expanduser(newdir))
    try:
        yield
    finally:
        os.chdir(prevdir)

def export_data(adj_val, filename, data_size=32, backup=None):
    data = []
    if data_size > 32:
        assert data_size % 32 == 0
        word_per_vtx = data_size//32
        for x in adj_val:
            for i in word_per_vtx:
                data.append(x & 0xFFFFFFFF)
                x >>= 32
    if data_size < 32:
        assert 32 % data_size == 0
        vtx_per_word = 32//data_size
        for i in range(len(adj_val)//vtx_per_word):
            data.append(pack(adj_val[i*vtx_per_word:(i+1)*vtx_per_word], wordsize=data_size))
    if data_size == 32:
        data = adj_val

    with open(filename, 'wb') as f1:
        if backup:
            f2 = open(backup, 'wb')
        for x in data:
            f1.write(struct.pack('=I', x))
            if backup:
                f2.write(struct.pack('=I', x))
