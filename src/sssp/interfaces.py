from migen import *
from migen.genlib.record import *


### user-defined ###

## message payload format

message_layout = [
    ("dist", "edgedatasize", DIR_M_TO_S)
]

update_layout = [
    ("dist", "edgedatasize", DIR_M_TO_S)
]


### Memory Interfaces ###

node_storage_layout = [
    ("dist", "edgedatasize"),
    ("parent", "nodeidsize"),
    ("active", 1)
]

edge_storage_layout = [
    ("dist", "edgedatasize")
]
