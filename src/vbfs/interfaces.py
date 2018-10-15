from migen import *
from migen.genlib.record import *


### user-defined ###

## message payload format (user-defined)

update_layout = message_layout = [
    ("dummy", 1, DIR_M_TO_S)
]

### Memory Interfaces ###

node_storage_layout = [
    ("parent", "nodeidsize"),
    ("active", 1)
]
