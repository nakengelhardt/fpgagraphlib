from migen import *

### user-defined ###

## message payload format

payload_layout = [
    ( "weight", "floatsize", DIR_M_TO_S )
]

## node storage

node_storage_layout = [
    ("nneighbors", "nodeidsize"),
    ("nrecvd", "nodeidsize"),
    ("sum", "floatsize")
]



def convert_int_to_record(n, record):
    s = bin(n)[2:]
    total_length = sum([length for _, length in record])
    if len(s) < total_length:
        s = '0'*(total_length-len(s)) + s
    res = {}
    curr_idx = 0
    for attr, length in record[::-1]:
        res[attr] = int(s[curr_idx:curr_idx+length], 2)
    return res