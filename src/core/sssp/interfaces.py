from migen import *
from migen.genlib.record import *


### user-defined ###

## message payload format (user-defined)

payload_layout = [
    ("dist", "edgedatasize", DIR_M_TO_S)
]

### Memory Interfaces ###

node_storage_layout = [
    ("dist", "edgedatasize"),
    ("parent", "nodeidsize")
]

edge_storage_layout = [
    ("dist", "edgedatasize")
]