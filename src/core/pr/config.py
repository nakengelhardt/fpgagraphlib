from migen import *
from migen.genlib.record import *

from tbsupport import convert_float_to_32b_int, convert_32b_int_to_float

from core_address import AddressLayout
from pr.interfaces import payload_layout, node_storage_layout
from pr.pr_applykernel import ApplyKernel
from pr.pr_scatterkernel import ScatterKernel


class Config:
    def __init__(self, adj_dict, quiet=False):
        # nodeidsize = 16
        # num_nodes_per_pe = 2**11
        # edgeidsize = 16
        # max_edges_per_pe = 2**14
        # peidsize = 3
        # num_pe = 1
        
        # nodeidsize = 16
        # num_nodes_per_pe = 2**10
        # edgeidsize = 16
        # max_edges_per_pe = 2**14
        # peidsize = 5
        # num_pe = 32

        # nodeidsize = 16
        # num_nodes_per_pe = 2**8
        # edgeidsize = 16
        # max_edges_per_pe = 2**12
        # peidsize = 5
        # num_pe = 8

        nodeidsize = 8
        num_nodes_per_pe = 2**4
        edgeidsize = 8
        max_edges_per_pe = 2**6
        peidsize = 1
        num_pe = 1

        floatsize = 32
        payloadsize = layout_len(set_layout_parameters(payload_layout, floatsize=floatsize))

        self.addresslayout = AddressLayout(nodeidsize=nodeidsize, edgeidsize=edgeidsize, peidsize=peidsize, num_pe=num_pe, num_nodes_per_pe=num_nodes_per_pe, max_edges_per_pe=max_edges_per_pe, payloadsize=payloadsize)
        self.addresslayout.floatsize = floatsize

        self.addresslayout.node_storage_layout_len = layout_len(set_layout_parameters(node_storage_layout, **self.addresslayout.get_params()))
        
        num_nodes = len(adj_dict)
        self.addresslayout.const_base = convert_float_to_32b_int(0.15/num_nodes)

        self.applykernel = ApplyKernel
        self.scatterkernel = ScatterKernel

        self.adj_dict = adj_dict

        self.init_nodedata = [0] + [len(self.adj_dict[node]) for node in range(1, num_nodes+1)] + [0 for _ in range(num_nodes+1, num_pe*num_nodes_per_pe)]
        
        init_messages = {}
        for node in self.adj_dict:
            pe = node >> log2_int(num_nodes_per_pe)
            if pe not in init_messages:
                init_messages[pe] = []
            init_messages[pe].append((node, self.addresslayout.const_base))
            
        self.init_messages = init_messages
        
        if not quiet:
            print("nodeidsize = {}\nedgeidsize = {}\npeidsize = {}".format(nodeidsize, edgeidsize, peidsize))
            print("num_pe = " + str(num_pe))
            print("num_nodes_per_pe = " + str(num_nodes_per_pe))
            print("max_edges_per_pe = " + str(max_edges_per_pe))

    def gen_monitor(self, tb):
        num_pe = len(tb.apply)
        level = [0 for _ in range(num_pe)]
        num_cycles = 0
        while not (yield tb.global_inactive):
            num_cycles += 1
            for i in range(num_pe):
                if (yield tb.apply[i].applykernel.barrier_out) and (yield tb.apply[i].applykernel.message_ack):
                    level[i] += 1
                    print("{}\tPE {} raised to level {}".format(num_cycles, i, level[i]))
                if (yield tb.apply[i].applykernel.message_valid) and (yield tb.apply[i].applykernel.message_ack):
                    print(str(num_cycles)+"\tNode " + str((yield tb.apply[i].applykernel.message_sender)) + " updated in round " + str(level[i]) +". New weight: " + str(convert_32b_int_to_float((yield tb.apply[i].applykernel.message_out.weight))))
                if (yield tb.apply[i].applykernel.valid_in) and (yield tb.apply[i].applykernel.ready) and not (yield tb.apply[i].applykernel.barrier_in):
                    print("{}\tMessage {} of {} for node {}".format(num_cycles, (yield tb.apply[i].applykernel.state_in.nrecvd)+1, (yield tb.apply[i].applykernel.state_in.nneighbors), (yield tb.apply[i].applykernel.nodeid_in)))
            yield
        print(str(num_cycles) + " cycles taken.")