from migen.fhdl.std import *
from migen.genlib.misc import optree

from bfs_interfaces import BFSScatterInterface, BFSMessage
from bfs_neighbors import BFSNeighbors

def make_test_graph(num_nodes_per_pe, max_edges_per_pe):
	## TODO
	return [(0,0) for i in range(num_nodes_per_pe)], [0 for i in range(max_edges_per_pe)]


class BFSScatter(Module):
	def __init__(self, num_pe, nodeidsize, num_nodes_per_pe, max_edges_per_pe, fifos, adj_mat=None):
		self.scatter_interface = BFSScatterInterface(nodeidsize)
		

		###
		def _pack_adj_idx(adj_idx):
			return [b<<log2_int(max_edges_per_pe) | a for a,b in adj_idx]

		if adj_mat != None:
			adj_idx, adj_val = adj_mat
		else:
			adj_idx, adj_val = make_test_graph(num_nodes_per_pe, max_edges_per_pe)

		# CSR edge storage: (idx, val) tuple of arrays
		# idx: array of (start_adr, num_neighbors)
		self.specials.mem_idx = Memory(log2_int(max_edges_per_pe) *2, num_nodes_per_pe, init=_pack_adj_idx(adj_idx))
		self.specials.rd_port_idx = rd_port_idx = self.mem_idx.get_port(has_re=True)
		# self.specials.wr_port_idx = wr_port_idx = self.mem_idx.get_port(write_capable=True)

		# val: array of nodeids
		# resides in submodule
		self.submodules.get_neighbors = BFSNeighbors(nodeidsize, num_nodes_per_pe, max_edges_per_pe, adj_val)


		stage1_ack = Signal()
		stage2_ack = Signal()
		stage3_ack = Signal()
		## stage 1

		# address idx with incoming message
		self.comb += rd_port_idx.adr.eq(self.scatter_interface.msg),rd_port_idx.re.eq(stage2_ack), self.scatter_interface.ack.eq(stage1_ack)
		self.comb += stage1_ack.eq(self.get_neighbors.ack)

		# keep input for next stage
		scatter_msg1 = Signal(nodeidsize)
		scatter_msg_valid1 = Signal()
		self.sync += If( stage1_ack , scatter_msg1.eq(self.scatter_interface.msg), scatter_msg_valid1.eq(self.scatter_interface.valid) )

		## stage 2


		self.comb += self.get_neighbors.start_idx.eq(rd_port_idx.dat_r[:log2_int(max_edges_per_pe)]), \
					 self.get_neighbors.num_neighbors.eq(rd_port_idx.dat_r[log2_int(max_edges_per_pe):]), \
					 self.get_neighbors.valid.eq(scatter_msg_valid1), \
					 stage2_ack.eq(self.get_neighbors.ack)

		# next stage read data valid
		scatter_msg2 = Signal(nodeidsize)
		scatter_msg_valid2 = Signal()
		self.sync += If( stage2_ack, scatter_msg2.eq(scatter_msg1), scatter_msg_valid2.eq(scatter_msg_valid1) )


		## stage 3

		array_dest_id = Array(fifo.din.dest_id for fifo in fifos)
		array_parent = Array(fifo.din.parent for fifo in fifos)
		array_we = Array(fifo.we for fifo in fifos)
		array_writable = Array(fifo.writable for fifo in fifos)

		# send out messages
		neighbor_pe = Signal(log2_int(num_pe))
		self.comb += neighbor_pe.eq(self.get_neighbors.neighbor[-log2_int(num_pe):])

		self.comb += self.get_neighbors.neighbor_ack.eq(stage3_ack), If(stage3_ack, 
			If(self.get_neighbors.neighbor_valid, 
				array_dest_id[neighbor_pe].eq(self.get_neighbors.neighbor),
				array_parent[neighbor_pe].eq(scatter_msg2),
				array_we[neighbor_pe].eq(1)
			)
		)

		# stall pipeline if not able to send
		self.comb += stage3_ack.eq(array_writable[neighbor_pe])
		

