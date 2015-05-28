from migen.fhdl.std import *
from migen.genlib.misc import optree

from bfs_interfaces import BFSScatterInterface, BFSMessage

def make_test_graph(num_nodes_per_pe, max_edges_per_pe):
	## TODO
	return [(0,0) for i in range(num_nodes_per_pe)], [0 for i in range(max_edges_per_pe)]


class BFSScatter(Module):
	def __init__(self, num_pe, nodeidsize, num_nodes_per_pe, max_edges_per_pe, fifo, adj_mat=None):
		self.scatter_interface = BFSScatterInterface(nodeidsize)
		

		###
		def _pack_adj_idx(adj_idx):
			return [b<<log2_int(max_edges_per_pe)|a for a,b in adj_idx]

		if adj_mat != None:
			adj_idx, adj_val = adj_mat
		else:
			adj_idx, adj_val = make_test_graph(num_nodes_per_pe, max_edges_per_pe)

		# CSR edge storage: (idx, val) tuple of arrays
		# idx: array of (start_adr, num_neighbors)
		self.specials.mem_idx = Memory(log2_int(max_edges_per_pe) *2, num_nodes_per_pe, init=_pack_adj_idx(adj_idx))
		self.specials.rd_port_idx = rd_port_idx = self.mem_idx.get_port()
		# self.specials.wr_port_idx = wr_port_idx = self.mem_idx.get_port(write_capable=True)

		# val: array of nodeids
		self.specials.mem_val = Memory(nodeidsize, max_edges_per_pe, init=adj_val)
		self.specials.rd_port_val = rd_port_val = self.mem_val.get_port()
		# self.specials.wr_port_val = wr_port_val = self.mem_val.get_port(write_capable=True)

		enable_pipeline = Signal()

		## stage 1

		# address idx with incoming message
		self.comb += rd_port_idx.adr.eq(self.scatter_interface.msg)

		# keep input for next stage
		scatter_msg1 = Signal(nodeidsize)
		scatter_msg_valid1 = Signal()
		self.sync += If( enable_pipeline & self.scatter_interface.we, scatter_msg1.eq(self.scatter_interface.msg), scatter_msg_valid1.eq(self.scatter_interface.we) )

		## stage 2

		# split (start_adr, num_neighbors)
		rd_node_idx = Signal(log2_int(max_edges_per_pe))
		rd_node_num_neighbors = Signal(log2_int(max_edges_per_pe))
		self.comb += rd_node_idx.eq(rd_port_idx.dat_r[:log2_int(max_edges_per_pe)]), rd_node_num_neighbors.eq(rd_port_idx.dat_r[log2_int(max_edges_per_pe):])

		# iterate over neighbors
		curr_node_idx = Signal(log2_int(max_edges_per_pe))
		end_node_idx = Signal(log2_int(max_edges_per_pe))
		idx_valid = Signal()
		stage2_done = Signal()

		self.comb += stage2_done.eq(curr_node_idx < end_node_idx)
		self.sync += If(enable_pipeline, 
			If( scatter_msg_valid1,
				curr_node_idx.eq(rd_port_idx),
				end_node_idx.eq(rd_port_idx + rd_node_num_neighbors - 1),
				idx_valid.eq(1)
			).Elif( stage2_done,
				curr_node_idx.eq(curr_node_idx + 1),
				idx_valid.eq(1)
			).Else(
				idx_valid.eq(0)
			)
		)

		self.comb += rd_port_val.adr.eq(curr_node_idx)

		# next stage read data valid
		val_valid = Signal()
		self.sync += val_valid.eq(idx_valid)
		scatter_msg2 = Signal(nodeidsize)
		scatter_msg_valid2 = Signal()
		self.sync += If( scatter_msg_valid1, scatter_msg2.eq(scatter_msg1), scatter_msg_valid2.eq(scatter_msg_valid1) )


		## stage 3

		# send out messages
		message = Signal(nodeidsize * 2)
		self.comb += message[:nodeidsize].eq(rd_port_val.dat_r), message[nodeidsize:].eq(scatter_msg1)
		self.comb += If(enable_pipeline, 
			If(val_valid, 
				fifo[rd_port_val.dat_r[-log2_int(num_pe):]].din.eq(message),
				fifo[rd_port_val.dat_r[-log2_int(num_pe):]].we.eq(1)
			)
		)

		# stall pipeline if might not be able to send
		self.comb += enable_pipeline.eq( ~ optree("&", [fifo[i].writable for i in range(len(fifo))]))
		

