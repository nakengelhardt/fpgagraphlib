from migen import *
from migen.genlib.record import *

from core_interfaces import ScatterInterface, NetworkInterface
from core_neighbors import Neighbors
from core_address import AddressLayout

class Scatter(Module):
    def __init__(self, config, adj_mat=None):
        addresslayout = config.addresslayout
        nodeidsize = addresslayout.nodeidsize
        num_nodes_per_pe = addresslayout.num_nodes_per_pe
        num_pe = addresslayout.num_pe
        edgeidsize = addresslayout.edgeidsize
        max_edges_per_pe = addresslayout.max_edges_per_pe
        peidsize = addresslayout.peidsize

        # input
        self.scatter_interface = ScatterInterface(**addresslayout.get_params())

        #output
        self.network_interface = NetworkInterface(**addresslayout.get_params())

        ###

        # memory layout (TODO: replace with an actual record)
        def _pack_adj_idx(adj_idx):
            return [b<<edgeidsize | a for a,b in adj_idx] if adj_idx else None

        if adj_mat != None:
            adj_idx, adj_val = adj_mat
        else:
            adj_idx, adj_val = None, None

        # CSR edge storage: (idx, val) tuple of arrays
        # idx: array of (start_adr, num_neighbors)
        self.specials.mem_idx = Memory(edgeidsize*2, num_nodes_per_pe, init=_pack_adj_idx(adj_idx))
        self.specials.rd_port_idx = rd_port_idx = self.mem_idx.get_port(has_re=True)
        self.specials.wr_port_idx = wr_port_idx = self.mem_idx.get_port(write_capable=True)

        # val: array of nodeids
        # resides in submodule
        self.submodules.get_neighbors = Neighbors(addresslayout, adj_val)


        # flow control variables
        upstream_ack = Signal()


        ## stage 1

        # address idx with incoming message
        self.comb += [
            rd_port_idx.adr.eq(addresslayout.local_adr(self.scatter_interface.sender)),
            rd_port_idx.re.eq(upstream_ack),
            self.scatter_interface.ack.eq(upstream_ack)
        ]

        # keep input for next stage
        scatter_msg1 = Signal(addresslayout.payloadsize)
        scatter_sender1 = Signal(addresslayout.nodeidsize)
        scatter_round1 = Signal()
        scatter_msg_valid1 = Signal()
        scatter_barrier1 = Signal()
        # valid1 requests get_neighbors, so don't set for barrier
        self.sync += If( upstream_ack,
                         scatter_msg1.eq(self.scatter_interface.payload),
                         scatter_sender1.eq(self.scatter_interface.sender),
                         scatter_round1.eq(self.scatter_interface.roundpar),
                         scatter_msg_valid1.eq(self.scatter_interface.valid & ~self.scatter_interface.barrier), 
                         scatter_barrier1.eq(self.scatter_interface.valid & self.scatter_interface.barrier) 
                     )

        ## stage 2

        # ask get_neighbors submodule for all neighbors of input node
        # upstream_ack will only go up again when all neighbors done
        self.comb +=[
            self.get_neighbors.start_idx.eq(rd_port_idx.dat_r[:edgeidsize]),
            self.get_neighbors.num_neighbors.eq(rd_port_idx.dat_r[edgeidsize:]),
            self.get_neighbors.valid.eq(scatter_msg_valid1),
            self.get_neighbors.barrier_in.eq(scatter_barrier1),
            self.get_neighbors.message_in.eq(scatter_msg1),
            self.get_neighbors.sender_in.eq(scatter_sender1),
            self.get_neighbors.round_in.eq(scatter_round1),
            upstream_ack.eq(self.get_neighbors.ack)
        ]


        ## stage 3

        # user modification based on edge data

        self.submodules.scatterkernel = config.scatterkernel(config.addresslayout)

        self.comb += [
            self.scatterkernel.message_in.raw_bits().eq(self.get_neighbors.message_out),
            self.scatterkernel.num_neighbors_in.eq(self.get_neighbors.num_neighbors_out),
            self.scatterkernel.neighbor_in.eq(self.get_neighbors.neighbor),
            self.scatterkernel.sender_in.eq(self.get_neighbors.sender_out),
            self.scatterkernel.round_in.eq(self.get_neighbors.round_out),
            self.scatterkernel.barrier_in.eq(self.get_neighbors.barrier_out),
            self.scatterkernel.valid_in.eq(self.get_neighbors.neighbor_valid),
            self.get_neighbors.neighbor_ack.eq(self.scatterkernel.ready)
        ]

        # find destination PE
        if num_pe > 1:
            neighbor_pe = Signal(peidsize)
            self.comb += neighbor_pe.eq(addresslayout.pe_adr(self.scatterkernel.neighbor_out))
        else:
            neighbor_pe = 0

        # send out messages
        self.comb += [
            self.network_interface.msg.dest_id.eq(self.scatterkernel.neighbor_out),
            self.network_interface.msg.payload.eq(self.scatterkernel.message_out.raw_bits()),
            self.network_interface.msg.sender.eq(self.scatterkernel.sender_out),
            self.network_interface.msg.roundpar.eq(self.scatterkernel.round_out),
            self.network_interface.msg.barrier.eq(self.scatterkernel.barrier_out),
            self.network_interface.broadcast.eq(self.scatterkernel.barrier_out),
            self.network_interface.valid.eq(self.scatterkernel.valid_out | self.scatterkernel.barrier_out),
            self.network_interface.dest_pe.eq(neighbor_pe),
            self.scatterkernel.message_ack.eq(self.network_interface.ack)
        ]