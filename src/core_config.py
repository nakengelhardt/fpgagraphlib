from migen import *
from tbsupport import *

from graph_manage import *
from core_address import AddressLayout

import logging
import datetime
import math

def max_edges_per_pe(adj_dict, num_pe, num_nodes_per_pe):
    max_pe = [0 for _ in range(num_pe)]
    for node in adj_dict:
        pe = node >> log2_int(num_nodes_per_pe)
        max_pe[pe] += len(adj_dict[node])
    return max(max_pe)

class CoreConfig:
    def __init__(self, graph, node_storage_layout, update_layout, message_layout, edge_storage_layout=None, has_edgedata=False, partition="random", partition_ufactor=1, use_hmc=False, use_ddr=False, updates_in_hmc=False, inverted=False, disable_filter=False, **kwargs):

        logger = logging.getLogger('init')

        self.has_edgedata = has_edgedata

        self.use_hmc = use_hmc
        self.use_ddr = use_ddr
        self.updates_in_hmc = updates_in_hmc
        self.disable_filter = disable_filter

        logger.info("Partition: {}".format(partition))
        if partition == "metis":
            assert kwargs["num_fpga"] > 1
            graph, num_nodes_per_pe = partition_metis(graph, kwargs["num_fpga"], kwargs["num_pe_per_fpga"], ufactor=partition_ufactor)
        elif partition == "greedy":

            graph, num_nodes_per_pe = partition_greedyedge(graph, kwargs["num_pe"])
        elif partition == "random" or partition == "robin":
            graph, num_nodes_per_pe = partition_random(graph, kwargs["num_pe"])
        else:
            logger.warning("Unrecognized partition option {} (options: metis, greedy, robin). Using roundrobin.".format(partition))
            graph, num_nodes_per_pe = partition_random(graph, kwargs["num_pe"])
        kwargs["num_nodes_per_pe"] = num_nodes_per_pe

        self.graph = graph
        self.adj_dict = make_adj_dict(graph)

        self.graph.graph['partition'] = partition

        if use_hmc or use_ddr:
            kwargs["max_edges_per_pe"] = 2**bits_for(len(graph.edges()))
        else:
            kwargs["max_edges_per_pe"] = 2**bits_for(max_edges_per_pe(self.adj_dict, kwargs["num_pe"], kwargs["num_nodes_per_pe"]))

        if "nodeidsize" not in kwargs:
            kwargs["nodeidsize"] = kwargs["peidsize"] + log2_int(kwargs["num_nodes_per_pe"])

        if "edgeidsize" not in kwargs:
            if use_ddr:
                kwargs["edgeidsize"] = 32
            elif use_hmc:
                kwargs["edgeidsize"] = 32
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
                if self.has_edgedata:
                    edgedatasize = self.addresslayout.edgedatasize
                else:
                    edgedatasize = 0
                assert (self.addresslayout.nodeidsize + edgedatasize) <= 128

                vertex_size = max(8,2**math.ceil(math.log2(self.addresslayout.nodeidsize + edgedatasize)))
                bytes_per_edge = vertex_size//8
                edges_per_burst = 16//bytes_per_edge
                print("vertex_size = {}, bytes_per_edge = {}, edges_per_burst = {}".format(vertex_size, bytes_per_edge, edges_per_burst))
                adj_idx, adj_val = self.addresslayout.generate_partition_flat(self.adj_dict, edges_per_burst=edges_per_burst, bytes_per_edge=bytes_per_edge, graph=graph)
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

        if has_edgedata and not use_hmc and not use_ddr:
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
        else:
            self.init_edgedata = []

    def summary(self):
        return "{}: {}inverted {} with {} using {} FPGA/{} PE dataset {} partition {}\n".format(
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "" if self.inverted else "non-",
            self.name,
            "DDR" if self.use_ddr else "HMC" if self.use_hmc else "BRAM",
            self.addresslayout.num_fpga, self.addresslayout.num_pe,
            self.graph.name,
            self.graph.graph['partition']
            )
