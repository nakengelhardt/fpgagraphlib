from migen.fhdl.std import *

from bfs_address import BFSAddressLayout


def config():
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
	num_nodes_per_pe = 2**3
	edgeidsize = 8
	max_edges_per_pe = 2**5
	peidsize = 1
	num_pe = 2

	payloadsize = nodeidsize

	print("nodeidsize = {}\nedgeidsize = {}\npeidsize = {}".format(nodeidsize, edgeidsize, peidsize))
	print("num_pe = " + str(num_pe))
	print("num_nodes_per_pe = " + str(num_nodes_per_pe))
	print("max_edges_per_pe = " + str(max_edges_per_pe))

	pcie_width = 128

	addresslayout = BFSAddressLayout(nodeidsize=nodeidsize, edgeidsize=edgeidsize, peidsize=peidsize, num_pe=num_pe, num_nodes_per_pe=num_nodes_per_pe, max_edges_per_pe=max_edges_per_pe, payloadsize=payloadsize)

	return addresslayout