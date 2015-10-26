from migen import *
from migen.genlib.record import *

from pr_address import PRAddressLayout
from pr_interfaces import payload_layout


def config(quiet=True):
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
    # peidsize = 8
    # num_pe = 8

    nodeidsize = 8
    num_nodes_per_pe = 2**4
    edgeidsize = 8
    max_edges_per_pe = 2**7
    peidsize = 3
    num_pe = 8

    floatsize = 32
    payloadsize = layout_len(set_layout_parameters(payload_layout, floatsize=floatsize))

    addresslayout = PRAddressLayout(nodeidsize=nodeidsize, edgeidsize=edgeidsize, peidsize=peidsize, num_pe=num_pe, num_nodes_per_pe=num_nodes_per_pe, max_edges_per_pe=max_edges_per_pe, payloadsize=payloadsize)
    
    addresslayout.floatsize = floatsize
    
    if not quiet:
        print("nodeidsize = {}\nedgeidsize = {}\npeidsize = {}".format(nodeidsize, edgeidsize, peidsize))
        print("num_pe = " + str(num_pe))
        print("num_nodes_per_pe = " + str(num_nodes_per_pe))
        print("max_edges_per_pe = " + str(max_edges_per_pe))

    return addresslayout