from migen.fhdl.std import *
from migen.genlib.record import *

## noc message format

_msg_layout = [
	( "barrier", 1, DIR_M_TO_S),
	( "dest_id", "nodeidsize", DIR_M_TO_S ),
	( "parent", "nodeidsize", DIR_M_TO_S )
]

class BFSMessage(Record):
	def __init__(self, nodeidsize):
		Record.__init__(self, set_layout_parameters(_msg_layout, nodeidsize=nodeidsize))

## interface between arbiter / apply

_apply_layout = [
	( "msg" , _msg_layout ),
	( "valid", 1, DIR_M_TO_S ),
	( "ack", 1, DIR_S_TO_M)
]

class BFSApplyInterface(Record):
	def __init__(self, nodeidsize):
		Record.__init__(self, set_layout_parameters(_apply_layout, nodeidsize=nodeidsize))


## interface between apply / scatter

_scatter_layout = [
	( "barrier", 1, DIR_M_TO_S),
	( "msg" ,"nodeidsize", DIR_M_TO_S ),
	( "valid", 1, DIR_M_TO_S ),
	( "ack", 1, DIR_S_TO_M)
]

class BFSScatterInterface(Record):
	def __init__(self, nodeidsize):
		Record.__init__(self, set_layout_parameters(_scatter_layout, nodeidsize=nodeidsize))

## interface between scatter / network

_network_layout = [
	( "msg" , _msg_layout ),
	( "dest_pe", "peidsize", DIR_M_TO_S ),
	( "broadcast", 1, DIR_M_TO_S),
	( "valid", 1, DIR_M_TO_S ),
	( "ack", 1, DIR_S_TO_M)
]

class BFSNetworkInterface(Record):
	def __init__(self, nodeidsize, peidsize):
		Record.__init__(self, set_layout_parameters(_network_layout, nodeidsize=nodeidsize, peidsize=peidsize))



