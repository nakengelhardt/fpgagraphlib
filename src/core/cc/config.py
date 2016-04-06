from migen import *

from core_address import AddressLayout
from cc.interfaces import node_storage_layout
from cc.applykernel import ApplyKernel
from cc.scatterkernel import ScatterKernel

class Config:
    def __init__(self, adj_dict, quiet=True):
        self.name = "cc"
        
        nodeidsize = 16
        num_nodes_per_pe = 2**11
        edgeidsize = 16
        max_edges_per_pe = 2**13
        num_pe = 16
        peidsize = log2_int(num_pe)
        pe_groups = 1
        inter_pe_delay = 0

        # nodeidsize = 16
        # num_nodes_per_pe = 2**13
        # edgeidsize = 16
        # max_edges_per_pe = 2**15
        # peidsize = 1
        # num_pe = 1
        # pe_groups = 4
        # inter_pe_delay = 256
        
        # nodeidsize = 16
        # num_nodes_per_pe = 2**10
        # edgeidsize = 16
        # max_edges_per_pe = 2**12
        # peidsize = 5
        # num_pe = 32

        # nodeidsize = 16
        # num_nodes_per_pe = 2**8
        # edgeidsize = 16
        # max_edges_per_pe = 2**12
        # peidsize = 8
        # num_pe = 8

        # nodeidsize = 8
        # num_nodes_per_pe = 2**6
        # edgeidsize = 16
        # max_edges_per_pe = 2**9
        # peidsize = 1
        # num_pe = 2

        payloadsize = nodeidsize

        self.addresslayout = AddressLayout(nodeidsize=nodeidsize, edgeidsize=edgeidsize, peidsize=peidsize, num_pe=num_pe, num_nodes_per_pe=num_nodes_per_pe, max_edges_per_pe=max_edges_per_pe, payloadsize=payloadsize)
        self.addresslayout.node_storage_layout_len = layout_len(set_layout_parameters(node_storage_layout, **self.addresslayout.get_params()))
        self.addresslayout.pe_groups = pe_groups
        self.addresslayout.inter_pe_delay = inter_pe_delay

        self.adj_dict = adj_dict
        adj_idx, adj_val = self.addresslayout.generate_partition(self.adj_dict)
        self.adj_idx = adj_idx
        self.adj_val = adj_val

        self.has_edgedata = False

        self.applykernel = ApplyKernel
        self.scatterkernel = ScatterKernel

        self.init_nodedata = [-1 for _ in range(num_pe*num_nodes_per_pe)]

        self.init_messages = [list() for _ in range(num_pe)]
        for node in self.adj_dict:
            pe = node >> log2_int(num_nodes_per_pe)
            self.init_messages[pe].append(({'dest_id':node, 'sender':0, 'payload':node}))


        if not quiet:
            print("nodeidsize = {}\nedgeidsize = {}\npeidsize = {}".format(nodeidsize, edgeidsize, peidsize))
            print("num_pe = " + str(num_pe))
            print("num_nodes_per_pe = " + str(num_nodes_per_pe))
            print("max_edges_per_pe = " + str(max_edges_per_pe))