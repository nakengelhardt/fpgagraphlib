from migen import *
from migen.genlib.record import *


### user-defined ###

## message payload format (user-defined)

message_layout = update_layout = [
    ("color", "nodeidsize", DIR_M_TO_S)
]

### Memory Interfaces ###

node_storage_layout = [
    ("color", "nodeidsize"),
    ("active", 1)
]
