from migen import *
from tbsupport import *

from graph_manage import *
from core_address import AddressLayout

import logging

def max_edges_per_pe(adj_dict, num_pe, num_nodes_per_pe):
    max_pe = [0 for _ in range(num_pe)]
    for node in adj_dict:
        pe = node >> log2_int(num_nodes_per_pe)
        max_pe[pe] += len(adj_dict[node])
    return max(max_pe)

class CoreConfig:
    def __init__(self, graph, node_storage_layout, update_layout, message_layout, edge_storage_layout=None, has_edgedata=False, partition_use_metis=False, partition_ufactor=20, use_hmc=False, use_ddr=False, updates_in_hmc=False, inverted=False, **kwargs):

        logger = logging.getLogger('init')

        self.has_edgedata = has_edgedata

        self.use_hmc = use_hmc
        self.use_ddr = use_ddr
        self.updates_in_hmc = updates_in_hmc

        if partition_use_metis:
            graph, num_nodes_per_pe = partition_metis(graph, kwargs["num_pe"], ufactor=partition_ufactor)
        else:
            graph, num_nodes_per_pe = partition_random(graph, kwargs["num_pe"])
        kwargs["num_nodes_per_pe"] =num_nodes_per_pe

        self.graph = graph
        self.adj_dict = make_adj_dict(graph)

        if use_hmc or use_ddr:
            kwargs["max_edges_per_pe"] = 2**bits_for(num_edges-1)
        else:
            kwargs["max_edges_per_pe"] = 2**bits_for(max_edges_per_pe(self.adj_dict, kwargs["num_pe"], kwargs["num_nodes_per_pe"]))

        if "nodeidsize" not in kwargs:
            kwargs["nodeidsize"] = kwargs["peidsize"] + log2_int(kwargs["num_nodes_per_pe"])

        if "edgeidsize" not in kwargs:
            if use_ddr:
                kwargs["edgeidsize"] = 33
            elif use_hmc:
                kwargs["edgeidsize"] = 34
            else:
                kwargs["edgeidsize"] = log2_int(kwargs["max_edges_per_pe"])

        self.addresslayout = AddressLayout(**kwargs)
        # Define the layouts.
        self.addresslayout.node_storage_layout = set_layout_parameters(node_storage_layout, **self.addresslayout.get_params())
        if has_edgedata:
            self.addresslayout.edge_storage_layout = set_layout_parameters(edge_storage_layout, **self.addresslayout.get_params())
            self.addresslayout.edgedatasize = layout_len(self.addresslayout.edge_storage_layout)
        self.addresslayout.updatepayloadsize = layout_len(set_layout_parameters(update_layout, **self.addresslayout.get_params()))
        self.addresslayout.messagepayloadsize = layout_len(set_layout_parameters(message_layout, **self.addresslayout.get_params()))



        # Set up the graph structure data
        self.inverted = inverted
        if inverted:
            if use_hmc:
                assert not self.has_edgedata
                adj_idx, adj_val = self.addresslayout.generate_partition_flat_inverted(self.adj_dict, edges_per_burst=4)
            elif use_ddr:
                assert not self.has_edgedata
                adj_idx, adj_val = self.addresslayout.generate_partition_flat_inverted(self.adj_dict, edges_per_burst=16)
            else:
                adj_idx, adj_val = self.addresslayout.generate_partition_inverted(self.adj_dict)
        else:
            if use_hmc:
                assert not self.has_edgedata
                adj_idx, adj_val = self.addresslayout.generate_partition_flat(self.adj_dict, edges_per_burst=4)
            elif use_ddr:
                assert not self.has_edgedata
                adj_idx, adj_val = self.addresslayout.generate_partition_flat(self.adj_dict, edges_per_burst=16)
            else:
                adj_idx, adj_val = self.addresslayout.generate_partition(self.adj_dict)
        self.adj_idx = adj_idx
        self.adj_val = adj_val
        self.start_addr = (1<<34)


        # Set up the init data

        max_node = self.addresslayout.max_node_per_pe(self.adj_dict)
        self.init_nodedata = [[0 for localid in range(max_node[pe] + 1)] for pe in range(self.addresslayout.num_pe)]
        for pe in range(self.addresslayout.num_pe):
            for localid in range(max_node[pe] + 1):
                node = self.addresslayout.global_adr(pe, localid)
                if node in graph:
                    self.init_nodedata[pe][localid] = convert_record_to_int(self.addresslayout.node_storage_layout, **graph.nodes[node])

        if has_edgedata:
            self.init_edgedata = [[0 for _ in range(len(adj_val[i]))] for i in range(self.addresslayout.num_pe)]
            for pe in range(self.addresslayout.num_pe):
                for localid, (idx, length) in enumerate(adj_idx[pe]):
                    if inverted:
                        node = localid
                    else:
                        node = self.addresslayout.global_adr(pe, localid)
                    for offset in range(length):
                        neighbor = adj_val[pe][idx+offset]
                        self.init_edgedata[pe][idx+offset] = convert_record_to_int(self.addresslayout.edge_storage_layout, **graph.get_edge_data(node, neighbor))
