from migen.fhdl.std import *
from migen.genlib.record import *

## noc message format

_msg_layout = [
	( "dest_id", "nodeidsize", DIR_M_TO_S ),
	( "parent", "nodeidsize", DIR_M_TO_S )
]

class BFSMessage(Record):
	def __init__(self, nodeidsize):
		Record.__init__(self, set_layout_parameters(_scatter_layout, nodeidsize=nodeidsize))

## interface between arbiter / apply

_apply_layout = [
	( "msg" , _msg_layout ),
	( "we", 1, DIR_M_TO_S ),
	( "ready", 1, DIR_S_TO_M)
]

class BFSApplyInterface(Record):
	def __init__(self, nodeidsize):
		Record.__init__(self, set_layout_parameters(_apply_layout, nodeidsize=nodeidsize))


## interface between apply / scatter

_scatter_layout = [
	( "msg" ,"nodeidsize", DIR_M_TO_S ),
	( "we", 1, DIR_M_TO_S ),
	( "ready", 1, DIR_S_TO_M)
]

class BFSScatterInterface(Record):
	def __init__(self, nodeidsize):
		Record.__init__(self, set_layout_parameters(_scatter_layout, nodeidsize=nodeidsize))


