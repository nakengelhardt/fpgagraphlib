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