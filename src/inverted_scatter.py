from migen import *
from migen.genlib.record import *

from core_interfaces import *

from core_neighbors import Neighbors
from core_neighbors_hmc import NeighborsHMC
from core_neighbors_ddr import NeighborsDDR

from core_address import AddressLayout

from recordfifo import *
from core_barrierdistributor import BarrierDistributor

class Scatter(Module):
    def __init__(self, pe_id, config, port=None):
        self.pe_id = pe_id
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
        self.apply_interface = ApplyInterface(**addresslayout.get_params())

        ###

        # # memory layout (TODO: replace with an actual record)
        def _pack_adj_idx(adj_idx):
            return [b<<edgeidsize | a for a,b in adj_idx]
        #
        # adj_idx, adj_val = adj_mat

        # CSR edge storage: (idx, val) tuple of arrays
        # idx: array of (start_adr, num_neighbors)
        self.specials.mem_idx = Memory(edgeidsize*2, max(2, len(config.adj_idx[pe_id])), name="edge_csr_idx", init=_pack_adj_idx(config.adj_idx[pe_id]))
        self.specials.rd_port_idx = rd_port_idx = self.mem_idx.get_port(has_re=True)
        self.specials.wr_port_idx = wr_port_idx = self.mem_idx.get_port(write_capable=True)

        # val: array of nodeids
        # resides in submodule

        if config.use_hmc:
            self.submodules.get_neighbors = NeighborsHMC(pe_id=pe_id, config=config, hmc_port=port)
        elif config.use_ddr:
            self.submodules.get_neighbors = NeighborsDDR(pe_id=pe_id, config=config, port=port)
        else:
            self.submodules.get_neighbors = Neighbors(pe_id=pe_id, config=config)


        # flow control variables
        upstream_ack = Signal()


        ## stage 1

        # address idx with incoming message
        self.comb += [
            rd_port_idx.adr.eq(self.scatter_interface.sender),
            rd_port_idx.re.eq(upstream_ack),
            self.scatter_interface.ack.eq(upstream_ack)
        ]

        # keep input for next stage
        scatter_msg1 = Signal(addresslayout.updatepayloadsize)
        scatter_sender1 = Signal(addresslayout.nodeidsize)
        scatter_round1 = Signal(config.addresslayout.channel_bits)
        scatter_msg_valid1 = Signal()
        scatter_barrier1 = Signal()
        # valid1 requests get_neighbors, so don't set for barrier
        self.sync += [
            If( upstream_ack,
                scatter_msg1.eq(self.scatter_interface.payload),
                scatter_sender1.eq(self.scatter_interface.sender),
                scatter_round1.eq(self.scatter_interface.roundpar),
                scatter_msg_valid1.eq(self.scatter_interface.valid & ~self.scatter_interface.barrier),
                scatter_barrier1.eq(self.scatter_interface.valid & self.scatter_interface.barrier)
            )
        ]

        ## stage 2

        # ask get_neighbors submodule for all neighbors of input node
        # upstream_ack will only go up again when all neighbors done
        self.comb +=[
            self.get_neighbors.neighbor_in.start_idx.eq(rd_port_idx.dat_r[:edgeidsize]),
            self.get_neighbors.neighbor_in.num_neighbors.eq(rd_port_idx.dat_r[edgeidsize:]),
            self.get_neighbors.neighbor_in.valid.eq(scatter_msg_valid1),
            self.get_neighbors.neighbor_in.barrier.eq(scatter_barrier1),
            self.get_neighbors.neighbor_in.message.eq(scatter_msg1),
            self.get_neighbors.neighbor_in.sender.eq(scatter_sender1),
            self.get_neighbors.neighbor_in.round.eq(scatter_round1),
            upstream_ack.eq(self.get_neighbors.neighbor_in.ack)
        ]


        ## stage 3

        # user modification based on edge data

        self.submodules.scatterkernel = config.scatterkernel(config)

        self.submodules.neighbor_out_fifo = InterfaceFIFO(layout=self.get_neighbors.neighbor_out.layout+([("edgedata", len(self.get_neighbors.edgedata_out), DIR_M_TO_S)] if config.has_edgedata else []), depth=8)


        self.comb += [
            self.get_neighbors.neighbor_out.connect(self.neighbor_out_fifo.din, omit={"valid", "edgedata"}),
            self.neighbor_out_fifo.din.valid.eq(self.get_neighbors.neighbor_out.valid | self.get_neighbors.neighbor_out.barrier),
            self.scatterkernel.update_in.raw_bits().eq(self.neighbor_out_fifo.dout.message),
            self.scatterkernel.num_neighbors_in.eq(self.neighbor_out_fifo.dout.num_neighbors),
            self.scatterkernel.neighbor_in.eq(self.neighbor_out_fifo.dout.neighbor),
            self.scatterkernel.sender_in.eq(self.neighbor_out_fifo.dout.sender),
            self.scatterkernel.round_in.eq(self.neighbor_out_fifo.dout.round),
            self.scatterkernel.barrier_in.eq(self.neighbor_out_fifo.dout.valid & self.neighbor_out_fifo.dout.barrier),
            self.scatterkernel.valid_in.eq(self.neighbor_out_fifo.dout.valid & ~self.neighbor_out_fifo.dout.barrier),
            self.neighbor_out_fifo.dout.ack.eq(self.scatterkernel.ready)
        ]
        if config.has_edgedata:
            self.comb += [
                self.neighbor_out_fifo.din.edgedata.eq(self.get_neighbors.edgedata_out),
                self.scatterkernel.edgedata_in.raw_bits().eq(self.neighbor_out_fifo.dout.edgedata)
            ]

        # scatterkernel output
        self.submodules.scatterkerneloutfifo = InterfaceFIFO(layout=self.apply_interface.layout, depth=8)

        self.comb += [
            self.scatterkerneloutfifo.din.msg.dest_id.eq(self.scatterkernel.neighbor_out),
            self.scatterkerneloutfifo.din.msg.payload.eq(self.scatterkernel.message_out.raw_bits()),
            self.scatterkerneloutfifo.din.msg.sender.eq(self.scatterkernel.sender_out),
            self.scatterkerneloutfifo.din.msg.roundpar.eq(self.scatterkernel.round_out),
            self.scatterkerneloutfifo.din.msg.barrier.eq(self.scatterkernel.barrier_out),
            self.scatterkerneloutfifo.din.valid.eq(self.scatterkernel.valid_out | self.scatterkernel.barrier_out),
            self.scatterkernel.message_ack.eq(self.scatterkerneloutfifo.din.ack),
        ]

        self.comb += self.scatterkerneloutfifo.dout.connect(self.apply_interface)

        self.total_num_messages = Signal(32)
        self.sync += [
            If(self.scatterkerneloutfifo.din.valid & self.scatterkerneloutfifo.din.ack,
                self.total_num_messages.eq(self.total_num_messages + 1)
            )
        ]
