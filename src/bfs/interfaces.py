from migen import *
from migen.genlib.record import *


### user-defined ###

## message payload format (user-defined)

message_layout = update_layout = [
    ("dummy", 1, DIR_M_TO_S)
]

### Memory Interfaces ###

node_storage_layout = [
    ("parent", "nodeidsize"),
    ("active", 1)
]
