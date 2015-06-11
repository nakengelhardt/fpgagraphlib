from migen.fhdl.std import *

class BFSAddressGenerator:
	"""Partition NodeID into PE number and local address"""
	def __init__(self, nodeidsize, num_pe, num_nodes_per_pe, max_edges_per_pe):
		assert nodeidsize >= log2_int(num_pe) + log2_int(num_nodes_per_pe)
		self.nodeidsize = nodeidsize
		self.num_pe = num_pe
		self.num_nodes_per_pe = num_nodes_per_pe

	def pe_adr(self, nodeid):
		return nodeid[log2_int(self.num_nodes_per_pe):log2_int(self.num_nodes_per_pe)+log2_int(self.num_pe)]

	def local_adr(self, nodeid):
		return nodeid[:log2_int(self.num_nodes_per_pe)]

	def partition(self, adj_mat, i):
		if adj_mat == None:
			return None
		adj_idx, adj_val = adj_mat

		# some PEs may only be partially filled, or even empty
		# ensure indexes do not exceed length of array
		num_nodes = len(adj_idx)
		assert num_nodes <= self.num_pe*self.num_nodes_per_pe
		idx_start = i*self.num_nodes_per_pe
		idx_end = min((i+1)*self.num_nodes_per_pe, num_nodes)

		if idx_start < num_nodes: # not empty
			val_start, _ = adj_idx[idx_start]
			endi, endo = adj_idx[idx_end - 1]
			val_end = endi + endo
			ret_idx = [ (i - val_start, n) for i,n in adj_idx[idx_start:idx_end]]
			ret_val = adj_val[val_start:val_end]
		else:
			ret_idx, ret_val = [], []
		return (ret_idx, ret_val)