from migen import *
from migen.genlib.record import *

from pr_interfaces import PRScatterInterface, PRNetworkInterface
from pr_neighbors import PRNeighbors
from pr_address import PRAddressLayout
from pr_config import config
from pr_scatterkernel import PRScatterKernel

class PRScatter(Module):
    def __init__(self, addresslayout, adj_mat=None):
        nodeidsize = addresslayout.nodeidsize
        num_nodes_per_pe = addresslayout.num_nodes_per_pe
        num_pe = addresslayout.num_pe
        edgeidsize = addresslayout.edgeidsize
        max_edges_per_pe = addresslayout.max_edges_per_pe
        peidsize = addresslayout.peidsize

        # input
        self.scatter_interface = PRScatterInterface(**addresslayout.get_params())

        #output
        self.network_interface = PRNetworkInterface(**addresslayout.get_params())

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
        self.submodules.get_neighbors = PRNeighbors(addresslayout, adj_val)


        # flow control variables
        stage1_ack = Signal()
        stage2_ack = Signal()


        ## stage 1

        # address idx with incoming message
        self.comb += rd_port_idx.adr.eq(addresslayout.local_adr(self.scatter_interface.sender)),rd_port_idx.re.eq(stage2_ack), self.scatter_interface.ack.eq(stage1_ack)
        self.comb += stage1_ack.eq(self.get_neighbors.ack)

        # keep input for next stage
        scatter_msg1 = Signal(addresslayout.payloadsize)
        scatter_msg_valid1 = Signal()
        scatter_barrier1 = Signal()
        # valid1 requests get_neighbors, so don't set for barrier
        self.sync += If( stage1_ack,
                         scatter_msg1.eq(self.scatter_interface.msg),
                         scatter_msg_valid1.eq(self.scatter_interface.valid & ~self.scatter_interface.barrier), 
                         scatter_barrier1.eq(self.scatter_interface.valid & self.scatter_interface.barrier) 
                     )

        ## stage 2

        # ask get_neighbors submodule for all neighbors of input node
        # stage2_ack will only go up again when all neighbors done
        self.comb +=[
            self.get_neighbors.start_idx.eq(rd_port_idx.dat_r[:edgeidsize]),
            self.get_neighbors.num_neighbors.eq(rd_port_idx.dat_r[edgeidsize:]),
            self.get_neighbors.valid.eq(scatter_msg_valid1),
            stage2_ack.eq(self.get_neighbors.ack)
        ]

        # keep input for next stage
        scatter_msg2 = Signal(addresslayout.payloadsize)
        scatter_msg_valid2 = Signal()
        scatter_barrier2 = Signal()
        num_neighbors2 = Signal(edgeidsize)
        self.sync += If( stage2_ack, 
                            scatter_msg2.eq(scatter_msg1), 
                            scatter_msg_valid2.eq(scatter_msg_valid1), 
                            scatter_barrier2.eq(scatter_barrier1),
                            num_neighbors2.eq(rd_port_idx.dat_r[edgeidsize:])
                        )


        ## stage 3

        # user modification based on edge data

        self.submodules.scatterkernel = PRScatterKernel(addresslayout)

        self.comb += [
            self.scatterkernel.message_in.raw_bits().eq(scatter_msg2),
            self.scatterkernel.num_neighbors_in.eq(num_neighbors2),
            self.scatterkernel.neighbor_in.eq(self.get_neighbors.neighbor),
            self.scatterkernel.barrier_in.eq(scatter_barrier2),
            self.scatterkernel.valid_in.eq(self.get_neighbors.neighbor_valid),
            self.get_neighbors.neighbor_ack.eq(self.scatterkernel.ready),

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
            self.network_interface.msg.barrier.eq(self.scatterkernel.barrier_out),
            self.network_interface.broadcast.eq(self.scatterkernel.barrier_out),
            self.network_interface.valid.eq(self.scatterkernel.valid_out | self.scatterkernel.barrier_out),
            self.network_interface.dest_pe.eq(neighbor_pe),
            self.scatterkernel.message_ack.eq(self.network_interface.ack)
        ]

if __name__ == "__main__":
    from migen.fhdl import verilog

    addresslayout = config()

    m = PRScatter(addresslayout)

    print(verilog.convert(m))

    print(addresslayout.get_params())