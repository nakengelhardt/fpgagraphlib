from migen import *

### user-defined ###

## message payload format

message_layout = update_layout = [
    ( "weight", "floatsize", DIR_M_TO_S )
]

## node storage

node_storage_layout = [
    ("nneighbors", "nodeidsize"),
    ("nrecvd", "nodeidsize"),
    ("sum", "floatsize"),
    ("active", 1)
]
