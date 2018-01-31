from migen import *

import logging

# import riffa
def unpack(data, n):
    words = []
    for i in range(n):
        words.append((data >> i*32) & 0xFFFFFFFF)
    return words

class AddressLayout:
    """Divide NodeID into PE number and local address"""
    def __init__(self, nodeidsize, edgeidsize, peidsize, num_pe, num_nodes_per_pe, max_edges_per_pe, payloadsize, **kwargs):
        assert nodeidsize >= peidsize + log2_int(num_nodes_per_pe)
        assert peidsize >= bits_for(num_pe)
        assert edgeidsize >= bits_for(max_edges_per_pe-1)
        self.nodeidsize = nodeidsize
        self.edgeidsize = edgeidsize
        self.peidsize = peidsize
        self.num_pe = num_pe
        self.num_nodes_per_pe = num_nodes_per_pe
        self.max_edges_per_pe = max_edges_per_pe
        self.payloadsize = payloadsize
        for k, v in kwargs.items():
            setattr(self, k, v)

    def get_params(self):
        return dict((key, getattr(self, key)) for key in dir(self) if key not in dir(self.__class__))

    def pe_adr(self, nodeid):
        if self.num_pe < 2:
            return 0
        if isinstance(nodeid, Signal):
            return nodeid[log2_int(self.num_nodes_per_pe):log2_int(self.num_nodes_per_pe)+self.peidsize]
        else:
            return nodeid >> log2_int(self.num_nodes_per_pe)

    def local_adr(self, nodeid):
        if isinstance(nodeid, Signal):
            return nodeid[:log2_int(self.num_nodes_per_pe)]
        else:
            return nodeid % self.num_nodes_per_pe

    def global_adr(self, pe_adr, local_adr):
        return (pe_adr << log2_int(self.num_nodes_per_pe)) | local_adr

    def max_per_pe(self, adj_dict):
        max_node = [0 for _ in range(self.num_pe)]
        for node in adj_dict:
            pe = node//self.num_nodes_per_pe
            localnode = node % self.num_nodes_per_pe
            if max_node[pe] < localnode:
                max_node[pe] = localnode
        return max_node

    def generate_partition(self, adj_dict):
        logger = logging.getLogger('config')
        max_node = self.max_per_pe(adj_dict)
        adj_idx = [[(0,0) for _ in range(max_node[pe] + 1)] for pe in range(self.num_pe)]
        adj_val = [[] for _ in range(self.num_pe)]

        for node, neighbors in adj_dict.items():
            pe = node//self.num_nodes_per_pe
            localnode = node % self.num_nodes_per_pe
            idx = len(adj_val[pe])
            n = len(neighbors)
            adj_idx[pe][localnode] = (idx, n)
            adj_val[pe].extend(neighbors)

        return adj_idx, adj_val

    def generate_partition_hmc(self, adj_dict):
        max_node = self.max_per_pe(adj_dict)
        adj_idx = [[(0,0) for _ in range(max_node[pe] + 1)] for pe in range(self.num_pe)]
        adj_val = []

        for node, neighbors in adj_dict.items():
            pe = node//self.num_nodes_per_pe
            localnode = node % self.num_nodes_per_pe
            idx = len(adj_val)
            n = len(neighbors)
            adj_idx[pe][localnode] = (idx*4, n)
            adj_val.extend(neighbors)
            if len(neighbors) % 4 != 0:
                adj_val.extend(0 for _ in range(4-(len(neighbors) % 4)))

        return adj_idx, adj_val

    def generate_partition_ddr(self, adj_dict):
        max_node = self.max_per_pe(adj_dict)
        adj_idx = [[(0,0) for _ in range(max_node[pe] + 1)] for pe in range(self.num_pe)]
        adj_val = []

        for node, neighbors in adj_dict.items():
            pe = node//self.num_nodes_per_pe
            localnode = node % self.num_nodes_per_pe
            idx = len(adj_val)
            n = len(neighbors)
            adj_idx[pe][localnode] = (idx*4, n)
            adj_val.extend(neighbors)
            if len(neighbors) % 16 != 0:
                adj_val.extend(0 for _ in range(16-(len(neighbors) % 16)))

        return adj_idx, adj_val

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
            word_sized_list.extend(unpack(x, pcie_width//32))

        return word_sized_list
