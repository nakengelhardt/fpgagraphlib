from migen import *
from migen.genlib.record import *

### Communication Interfaces ###

## noc message format

_msg_layout = [
    ( "halt", 1, DIR_M_TO_S),
    ( "barrier", 1, DIR_M_TO_S ),
    ( "roundpar", "channel_bits", DIR_M_TO_S ),
    ( "dest_id", "nodeidsize", DIR_M_TO_S ),
    ( "sender", "nodeidsize", DIR_M_TO_S ),
    ( "payload", "payloadsize", DIR_M_TO_S )
]

class Message(Record):
    def __init__(self, name=None, **kwargs):
        Record.__init__(self, set_layout_parameters(_msg_layout, **kwargs), name=name)

## interface between arbiter / apply

_apply_layout = [
    ( "msg" , _msg_layout ),
    ( "valid", 1, DIR_M_TO_S ),
    ( "ack", 1, DIR_S_TO_M)
]

class ApplyInterface(Record):
    def __init__(self, name=None, **kwargs):
        Record.__init__(self, set_layout_parameters(_apply_layout, **kwargs), name=name)


## interface between apply / scatter

_scatter_layout = [
    ( "barrier", 1, DIR_M_TO_S),
    ( "valid", 1, DIR_M_TO_S ),
    ( "ack", 1, DIR_S_TO_M ),
    ( "roundpar", "channel_bits", DIR_M_TO_S ),
    ( "sender", "nodeidsize", DIR_M_TO_S ),
    ( "payload", "payloadsize", DIR_M_TO_S )
]

class ScatterInterface(Record):
    def __init__(self, name=None, **kwargs):
        Record.__init__(self, set_layout_parameters(_scatter_layout, **kwargs), name=name)

_neighbor_in_layout = [
    ("start_idx", "edgeidsize", DIR_M_TO_S),
    ("num_neighbors", "edgeidsize", DIR_M_TO_S),
    ("sender", "nodeidsize", DIR_M_TO_S),
    ("message", "payloadsize", DIR_M_TO_S),
    ("round", "channel_bits", DIR_M_TO_S),
    ("barrier", 1, DIR_M_TO_S),
    ("valid", 1, DIR_M_TO_S),
    ("ack", 1, DIR_S_TO_M)
]

_neighbor_out_layout = [
    ("neighbor", "nodeidsize", DIR_M_TO_S),
    ("num_neighbors", "nodeidsize", DIR_M_TO_S),
    ("sender", "nodeidsize", DIR_M_TO_S),
    ("message", "payloadsize", DIR_M_TO_S),
    ("round", "channel_bits", DIR_M_TO_S),
    ("barrier", 1, DIR_M_TO_S),
    ("valid", 1, DIR_M_TO_S),
    ("ack", 1, DIR_S_TO_M)
]


## interface between scatter / network

_network_layout = [
    ( "msg" , _msg_layout ),
    ( "dest_pe", "peidsize", DIR_M_TO_S ),
    ( "special", 1, DIR_M_TO_S),
    ( "valid", 1, DIR_M_TO_S ),
    ( "ack", 1, DIR_S_TO_M)
]

class NetworkInterface(Record):
    def __init__(self, name=None, **kwargs):
        Record.__init__(self, set_layout_parameters(_network_layout, **kwargs), name=name)
