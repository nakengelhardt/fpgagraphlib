from migen.fhdl.std import *
from migen.genlib.record import *

## message payload format (user-defined)

payload_layout = [
	( "parent", "nodeidsize", DIR_M_TO_S )
]

## noc message format

_msg_layout = [
	( "barrier", 1, DIR_M_TO_S),
	( "dest_id", "nodeidsize", DIR_M_TO_S )
] + payload_layout

class BFSMessage(Record):
	def __init__(self, **kwargs):
		Record.__init__(self, set_layout_parameters(_msg_layout, **kwargs))

## interface between arbiter / apply

_apply_layout = [
	( "msg" , _msg_layout ),
	( "valid", 1, DIR_M_TO_S ),
	( "ack", 1, DIR_S_TO_M)
]

class BFSApplyInterface(Record):
	def __init__(self, **kwargs):
		Record.__init__(self, set_layout_parameters(_apply_layout, **kwargs))


## interface between apply / scatter

_scatter_layout = [
	( "barrier", 1, DIR_M_TO_S),
	( "valid", 1, DIR_M_TO_S ),
	( "ack", 1, DIR_S_TO_M)
] + payload_layout

class BFSScatterInterface(Record):
	def __init__(self, **kwargs):
		Record.__init__(self, set_layout_parameters(_scatter_layout, **kwargs))

## interface between scatter / network

_network_layout = [
	( "msg" , _msg_layout ),
	( "dest_pe", "peidsize", DIR_M_TO_S ),
	( "broadcast", 1, DIR_M_TO_S),
	( "valid", 1, DIR_M_TO_S ),
	( "ack", 1, DIR_S_TO_M)
]

class BFSNetworkInterface(Record):
	def __init__(self, **kwargs):
		Record.__init__(self, set_layout_parameters(_network_layout, **kwargs))



