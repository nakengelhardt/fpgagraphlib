from migen import *

import logging

from tbsupport import convert_record_to_int

# import riffa
def unpack(data, n):
    words = []
    for i in range(n):
        words.append((data >> i*32) & 0xFFFFFFFF)
    return words

class AddressLayout:
    """Divide NodeID into PE number and local address"""
    def __init__(self, nodeidsize, edgeidsize, peidsize, num_pe, num_nodes_per_pe, max_edges_per_pe, **kwargs):
        assert nodeidsize >= peidsize + log2_int(num_nodes_per_pe)
        assert peidsize >= bits_for(num_pe)
        assert edgeidsize >= bits_for(max_edges_per_pe-1)
        self.nodeidsize = nodeidsize
        self.edgeidsize = edgeidsize
        self.peidsize = peidsize
        self.num_pe = num_pe
        self.num_nodes_per_pe = num_nodes_per_pe
        self.max_edges_per_pe = max_edges_per_pe
        for k, v in kwargs.items():
            setattr(self, k, v)

        self.adj_val_entry_size_in_bytes = 0

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

    def fpga_adr(self, nodeid):
        pe = self.pe_adr(nodeid)
        fpga = 0
        while pe >= self.num_pe_per_fpga:
            pe -= self.num_pe_per_fpga
            fpga += 1
        return fpga

    def max_node_per_pe(self, adj_dict):
        max_node = [0 for _ in range(self.num_pe)]
        for node in adj_dict:
            pe = self.pe_adr(node)
            localnode = self.local_adr(node)
            if max_node[pe] < localnode:
                max_node[pe] = localnode
        return max_node

    def max_node(self, adj_dict):
        max_node = 0
        for node in adj_dict:
            if max_node < node:
                max_node = node
        return max_node

    def generate_partition(self, adj_dict):
        logger = logging.getLogger('config')
        max_node = self.max_node_per_pe(adj_dict)
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

    def generate_partition_flat(self, adj_dict, edges_per_burst=1, bytes_per_edge=4, graph=None):
        if hasattr(self, "edgedatasize"):
            edgedatasize = self.edgedatasize
        else:
            edgedatasize = 0
        assert (self.nodeidsize + edgedatasize) <= bytes_per_edge*8
        max_node = self.max_node_per_pe(adj_dict)
        adj_idx = [[(0,0) for _ in range(max_node[pe] + 1)] for pe in range(self.num_pe)]
        adj_val = []

        self.adj_val_entry_size_in_bytes = bytes_per_edge

        for node, neighbors in adj_dict.items():
            pe = node//self.num_nodes_per_pe
            localnode = node % self.num_nodes_per_pe
            idx = len(adj_val)
            n = len(neighbors)
            adj_idx[pe][localnode] = (idx*bytes_per_edge, n)
            if edgedatasize > 0:
                adj_val.extend([convert_record_to_int([('vtx', self.nodeidsize), ('data', edgedatasize)], vtx=v, data=convert_record_to_int(self.edge_storage_layout, **graph.get_edge_data(node, v))) for v in neighbors])
            else:
                adj_val.extend(neighbors)
            if len(neighbors) % edges_per_burst != 0:
                adj_val.extend(0 for _ in range(edges_per_burst-(len(neighbors) % edges_per_burst)))

        return adj_idx, adj_val

    def generate_partition_inverted(self, adj_dict):
        len_nodes = self.max_node(adj_dict) + 1
        adj_idx = [[(0,0) for _ in range(len_nodes)] for pe in range(self.num_pe)]
        adj_val = [[] for _ in range(self.num_pe)]

        for node, neighbors in adj_dict.items():
            subneighbors = [list() for _ in range(self.num_pe)]
            for n in neighbors:
                pe = self.pe_adr(n)
                subneighbors[pe].append(n)
            for pe in range(self.num_pe):
                idx = len(adj_val[pe])
                n = len(subneighbors[pe])
                adj_idx[pe][node] = (idx, n)
                adj_val[pe].extend(subneighbors[pe])

        return adj_idx, adj_val

    def generate_partition_flat_inverted(self, adj_dict, edges_per_burst=1, bytes_per_edge=4):
        len_nodes = self.max_node(adj_dict) + 1
        adj_idx = [[(0,0) for _ in range(len_nodes)] for pe in range(self.num_pe)]
        adj_val = []

        for node, neighbors in adj_dict.items():
            subneighbors = [list() for _ in range(self.num_pe)]
            for n in neighbors:
                pe = self.pe_adr(n)
                subneighbors[pe].append(n)
            for pe in range(self.num_pe):
                idx = len(adj_val)
                n = len(subneighbors[pe])
                adj_idx[pe][node] = (idx*bytes_per_edge, n)
                adj_val.extend(subneighbors[pe])
                if len(subneighbors[pe]) % edges_per_burst != 0:
                    adj_val.extend(0 for _ in range(edges_per_burst-(len(subneighbors[pe]) % edges_per_burst)))
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
