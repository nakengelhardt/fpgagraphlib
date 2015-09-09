from migen.fhdl.std import *

import riffa

class PRAddressLayout:
	"""Partition NodeID into PE number and local address"""
	def __init__(self, nodeidsize, edgeidsize, peidsize, num_pe, num_nodes_per_pe, max_edges_per_pe, payloadsize, **kwargs):
		assert nodeidsize >= peidsize + log2_int(num_nodes_per_pe)
		assert peidsize >= bits_for(num_pe-1)
		assert edgeidsize >= bits_for(max_edges_per_pe-1)
		self.nodeidsize = nodeidsize
		self.edgeidsize = edgeidsize
		self.peidsize = peidsize
		self.num_pe = num_pe
		self.num_nodes_per_pe = num_nodes_per_pe
		self.max_edges_per_pe = max_edges_per_pe
		self.payloadsize = payloadsize
		for k, v in kwargs:
			setattr(self, k, v)

	def get_params(self):
		return dict((key, getattr(self, key)) for key in dir(self) if key not in dir(self.__class__))

	def pe_adr(self, nodeid):
		return nodeid[log2_int(self.num_nodes_per_pe):log2_int(self.num_nodes_per_pe)+self.peidsize]

	def local_adr(self, nodeid):
		return nodeid[:log2_int(self.num_nodes_per_pe)]

	def global_adr(self, pe_adr, local_adr):
		return (pe_adr << log2_int(self.num_nodes_per_pe)) | local_adr

	def generate_partition(self, adj_dict):
		adj_idx = [[(0,0) for _ in range(self.num_nodes_per_pe)] for _ in range(self.num_pe)]
		adj_val = [[] for _ in range(self.num_pe)]

		for node, neighbors in adj_dict.items():
			pe = node//self.num_nodes_per_pe
			localnode = node % self.num_nodes_per_pe
			idx = len(adj_val[pe])
			n = len(neighbors)
			adj_idx[pe][localnode] = (idx, n)
			adj_val[pe].extend(neighbors)

		print("Graph has {} nodes and {} edges.".format(len(adj_dict), sum(len(a) for a in adj_val)//2))

		for i in range(len(adj_val)):
			if len(adj_val[i]) > self.max_edges_per_pe:
				print("Warning: adjacency list for PE {} exceeds storage. Extend max_edges_per_pe to more than {}.".format(i, len(adj_val[i])))
				adj_val[i] = adj_val[i][0:self.max_edges_per_pe]
			else:
				adj_val[i].extend([0 for _ in range(len(adj_val[i]), self.max_edges_per_pe)])
			assert len(adj_val[i]) == self.max_edges_per_pe
			assert len(adj_idx[i]) == self.num_nodes_per_pe 

		return adj_idx, adj_val

	def generate_partition_flat(self, adj_dict):
		adj_idx, adj_val = self.generate_partition(adj_dict)

		return [n<<self.edgeidsize | idx for sublist in adj_idx for (idx,n) in sublist], [item for sublist in adj_val for item in sublist]

	def repack(self, l, wordsize, pcie_width):
		words_per_line = pcie_width//wordsize
		pcie_sized_list = []
		for j in range(len(l)//words_per_line):
			x = 0
			for i in reversed(range(words_per_line)):
				x = x << wordsize | l[j*words_per_line + i]
			pcie_sized_list.append(x)

		word_sized_list = []
		for x in pcie_sized_list:
			word_sized_list.extend(riffa.unpack(x, pcie_width//32))

		return word_sized_list