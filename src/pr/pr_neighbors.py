from migen import *
from migen.genlib.fsm import FSM, NextState, NextValue

class PRNeighbors(Module):
    def __init__(self, addresslayout, adj_val):
        nodeidsize = addresslayout.nodeidsize
        num_nodes_per_pe = addresslayout.num_nodes_per_pe
        num_pe = addresslayout.num_pe
        edgeidsize = addresslayout.edgeidsize
        max_edges_per_pe = addresslayout.max_edges_per_pe

        # input
        self.start_idx = Signal(edgeidsize)
        self.num_neighbors = Signal(edgeidsize)
        self.valid = Signal()
        self.ack = Signal()

        # output
        self.neighbor = Signal(nodeidsize)
        self.neighbor_valid = Signal()
        self.neighbor_ack = Signal()
        ###

        # adjacency list storage (second half of CSR storage, index comes from input)
        # val: array of nodeids
        self.specials.mem_val = Memory(nodeidsize, max_edges_per_pe, init=adj_val)
        self.specials.rd_port_val = rd_port_val = self.mem_val.get_port()
        self.specials.wr_port_val = wr_port_val = self.mem_val.get_port(write_capable=True)


        curr_node_idx = Signal(edgeidsize)
        end_node_idx = Signal(edgeidsize)
        idx_valid = Signal()
        last_neighbor = Signal()

        # control path
        self.submodules.fsm = fsm = FSM()
        fsm.act("IDLE", # wait for input
            idx_valid.eq(0),
            self.ack.eq(1),
            If(self.valid & (self.num_neighbors != 0),
                NextValue(curr_node_idx, self.start_idx),
                NextValue(end_node_idx, self.start_idx + self.num_neighbors - 1),
                NextState("GET_NEIGHBORS")
            )
        )
        fsm.act("GET_NEIGHBORS", # iterate over neighbors
            self.ack.eq(0),
            idx_valid.eq(1),
            If(self.neighbor_ack,
                If(last_neighbor,
                    NextValue(curr_node_idx, 0),
                    NextValue(end_node_idx, 0),
                    NextState("IDLE")
                ).Else(
                    NextValue(curr_node_idx, curr_node_idx + 1)
                )
            )
        )

        # data path
        self.comb += last_neighbor.eq(~(curr_node_idx < end_node_idx))

        self.comb += rd_port_val.adr.eq(curr_node_idx)
        self.comb += self.neighbor.eq(rd_port_val.dat_r)

        # read port is valid if previous cycle's address was valid
        self.sync += self.neighbor_valid.eq(idx_valid)

        