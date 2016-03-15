from migen import *
from migen.genlib.record import *

from tbsupport import convert_float_to_32b_int, convert_32b_int_to_float, convert_int_to_record

from core_address import AddressLayout
from pr.interfaces import payload_layout, node_storage_layout
from pr.pr_applykernel import ApplyKernel
from pr.pr_scatterkernel import ScatterKernel



class Config:
    def __init__(self, adj_dict, quiet=False):
        self.name = "pr"
        
        # nodeidsize = 16
        # num_nodes_per_pe = 2**11
        # edgeidsize = 16
        # max_edges_per_pe = 2**13
        # num_pe = 16
        # peidsize = log2_int(num_pe)
        pe_groups = 4
        inter_pe_delay = 0
        
        # nodeidsize = 16
        # num_nodes_per_pe = 2**10
        # edgeidsize = 16
        # max_edges_per_pe = 2**14
        # num_pe = 32
        # peidsize = log2_int(num_pe)

        # nodeidsize = 16
        # num_nodes_per_pe = 2**8
        # edgeidsize = 16
        # max_edges_per_pe = 2**12
        # num_pe = 8
        # peidsize = log2_int(num_pe)

        nodeidsize = 8
        num_nodes_per_pe = 2**6
        edgeidsize = 8
        max_edges_per_pe = 2**8
        peidsize = 1
        num_pe = 2

        assert(num_pe * num_nodes_per_pe > len(adj_dict))

        floatsize = 32
        payloadsize = layout_len(set_layout_parameters(payload_layout, floatsize=floatsize))

        self.addresslayout = AddressLayout(nodeidsize=nodeidsize, edgeidsize=edgeidsize, peidsize=peidsize, num_pe=num_pe, num_nodes_per_pe=num_nodes_per_pe, max_edges_per_pe=max_edges_per_pe, payloadsize=payloadsize)
        self.addresslayout.floatsize = floatsize
        self.addresslayout.pe_groups = pe_groups
        self.addresslayout.inter_pe_delay = inter_pe_delay

        self.addresslayout.node_storage_layout_len = layout_len(set_layout_parameters(node_storage_layout, **self.addresslayout.get_params()))

        num_nodes = len(adj_dict)
        self.addresslayout.const_base = convert_float_to_32b_int(0.15/num_nodes)

        self.applykernel = ApplyKernel
        self.scatterkernel = ScatterKernel

        self.adj_dict = adj_dict

        self.init_nodedata = [0] + [len(self.adj_dict[node]) for node in range(1, num_nodes+1)] + [0 for _ in range(num_nodes+1, num_pe*num_nodes_per_pe)]

        init_messages = [list() for _ in range(num_pe)]
        for node in self.adj_dict:
            pe = node >> log2_int(num_nodes_per_pe)
            init_messages[pe].append(({'dest_id':node, 'sender':0, 'payload':self.addresslayout.const_base}))

        self.init_messages = init_messages

        if not quiet:
            print("nodeidsize = {}\nedgeidsize = {}\npeidsize = {}".format(nodeidsize, edgeidsize, peidsize))
            print("num_pe = " + str(num_pe))
            print("num_nodes_per_pe = " + str(num_nodes_per_pe))
            print("max_edges_per_pe = " + str(max_edges_per_pe))
            print("inter_pe_delay =", inter_pe_delay)
