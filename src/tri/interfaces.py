from migen import *
from migen.genlib.record import *


### user-defined ###

## message payload format (user-defined)

message_layout = update_layout = [
    ("origin", "nodeidsize", DIR_M_TO_S),
    ("hops", 2, DIR_M_TO_S)
]

### Memory Interfaces ###

node_storage_layout = [
    ("send_in_level", 16),
    ("num_triangles", 32),
    ("active", 1)
]

edge_storage_layout = [
    ("degree", "nodeidsize")
]
