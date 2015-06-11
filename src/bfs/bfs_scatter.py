from migen.fhdl.std import *
from migen.genlib.misc import optree

from bfs_interfaces import BFSScatterInterface, BFSMessage, BFSNetworkInterface
from bfs_neighbors import BFSNeighbors
from bfs_address import BFSAddressGenerator

class BFSScatter(Module):
	def __init__(self, num_pe, nodeidsize, num_nodes_per_pe, max_edges_per_pe, adj_mat=None):
		# input
		self.scatter_interface = BFSScatterInterface(nodeidsize)

		#output
		self.network_interface = BFSNetworkInterface(nodeidsize, log2_int(num_pe))

		###

		# memory layout (TODO: replace with an actual record)
		def _pack_adj_idx(adj_idx):
			return [b<<log2_int(max_edges_per_pe) | a for a,b in adj_idx] if adj_idx else None

		if adj_mat != None:
			adj_idx, adj_val = adj_mat
		else:
			adj_idx, adj_val = None, None

		# CSR edge storage: (idx, val) tuple of arrays
		# address format handler
		addressgenerator = BFSAddressGenerator(nodeidsize, num_pe, num_nodes_per_pe)
		# idx: array of (start_adr, num_neighbors)
		self.specials.mem_idx = Memory(log2_int(max_edges_per_pe) *2, num_nodes_per_pe, init=_pack_adj_idx(adj_idx))
		self.specials.rd_port_idx = rd_port_idx = self.mem_idx.get_port(has_re=True)
		self.specials.wr_port_idx = wr_port_idx = self.mem_idx.get_port(write_capable=True)

		# val: array of nodeids
		# resides in submodule
		self.submodules.get_neighbors = BFSNeighbors(nodeidsize, num_nodes_per_pe, max_edges_per_pe, adj_val)


		# flow control variables
		stage1_ack = Signal()
		stage2_ack = Signal()
		stage3_ack = Signal()


		## stage 1


		# address idx with incoming message
		self.comb += rd_port_idx.adr.eq(addressgenerator.local_adr(self.scatter_interface.msg)),rd_port_idx.re.eq(stage2_ack), self.scatter_interface.ack.eq(stage1_ack)
		self.comb += stage1_ack.eq(self.get_neighbors.ack)

		# keep input for next stage
		scatter_msg1 = Signal(nodeidsize)
		scatter_msg_valid1 = Signal()
		self.sync += If( stage1_ack , scatter_msg1.eq(self.scatter_interface.msg), scatter_msg_valid1.eq(self.scatter_interface.valid) )

		## stage 2

		# ask get_neighbors submodule for all neighbors of input node
		# stage2_ack will only go up again when all neighbors done
		self.comb += self.get_neighbors.start_idx.eq(rd_port_idx.dat_r[:log2_int(max_edges_per_pe)]), \
					 self.get_neighbors.num_neighbors.eq(rd_port_idx.dat_r[log2_int(max_edges_per_pe):]), \
					 self.get_neighbors.valid.eq(scatter_msg_valid1), \
					 stage2_ack.eq(self.get_neighbors.ack)

		# keep input for next stage
		scatter_msg2 = Signal(nodeidsize)
		scatter_msg_valid2 = Signal()
		self.sync += If( stage2_ack, scatter_msg2.eq(scatter_msg1), scatter_msg_valid2.eq(scatter_msg_valid1) )


		## stage 3

		# TODO: formalize address fields
		if num_pe > 1:
			neighbor_pe = Signal(log2_int(num_pe))
			self.comb += neighbor_pe.eq(addressgenerator.pe_adr(self.get_neighbors.neighbor))
		else:
			neighbor_pe = 0

		# send out messages
		self.comb += self.get_neighbors.neighbor_ack.eq(stage3_ack), \
					 self.network_interface.msg.dest_id.eq(self.get_neighbors.neighbor),\
					 self.network_interface.msg.parent.eq(scatter_msg2),\
					 self.network_interface.valid.eq(self.get_neighbors.neighbor_valid),\
					 self.network_interface.dest_pe.eq(neighbor_pe),\
					 stage3_ack.eq(self.network_interface.ack)


