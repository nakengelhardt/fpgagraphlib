from migen.fhdl.std import *

from migen.sim.generic import run_simulation

from bfs_top import BFS
from bfs_address import BFSAddressLayout
from bfs_graph_input import read_graph

import riffa

import sys

class TB(Module):
	def __init__(self, graphfile=None):

		nodeidsize = 16
		num_nodes_per_pe = 2**8
		edgeidsize = 16
		max_edges_per_pe = 2**12
		peidsize = 8
		num_pe = 8

		# nodeidsize = 8
		# num_nodes_per_pe = 2**2
		# edgeidsize = 8
		# max_edges_per_pe = 2**4
		# peidsize = 1
		# num_pe = 2

		self.pcie_width = 128

		if graphfile:
			self.adj_dict = read_graph(graphfile)
		else:
			self.adj_dict = {1:[2,3,4], 2:[1,5,6], 3:[1,4,7], 4:[1,3,5], 5:[2,4,6], 6:[2,5,7], 7:[3,6]}

		self.addresslayout = BFSAddressLayout(nodeidsize, edgeidsize, peidsize, num_pe, num_nodes_per_pe, max_edges_per_pe)

		self.rx = riffa.Interface(data_width=self.pcie_width)
		self.tx = riffa.Interface(data_width=self.pcie_width)
		dummy_rx = Signal()
		dummy_tx = Signal()
		self.comb += dummy_rx.eq(self.rx.raw_bits()), dummy_tx.eq(self.tx.raw_bits())

		self.submodules.dut = BFS(self.addresslayout, self.rx, self.tx)

	def gen_simulation(self, selfp):
		adj_idx, adj_val = self.addresslayout.generate_partition_flat(self.adj_dict)
		# print("adj_idx: " + str([hex(x) for x in adj_idx]))
		# print("adj_val: " + str(adj_val))
		adj_idx_flat = self.addresslayout.repack(adj_idx, 2*self.addresslayout.edgeidsize, self.pcie_width)
		adj_val_flat = self.addresslayout.repack(adj_val, self.addresslayout.nodeidsize, self.pcie_width)
		# print("adj_idx_flat: " + str([hex(x) for x in adj_idx_flat]))
		# print("adj_val_flat: " + str([hex(x) for x in adj_val_flat]))

		yield from riffa.channel_write(selfp.simulator, self.rx, adj_idx_flat)
		yield from riffa.channel_write(selfp.simulator, self.rx, adj_val_flat)

		# check nodes are visited
		num_visited = 0
		num_nodes = len(self.adj_dict)
		while selfp.dut.global_inactive==0:
			for i in range(self.addresslayout.num_pe):
				if selfp.dut.scatter[i].scatter_interface.valid & selfp.dut.scatter[i].scatter_interface.ack:
					if not selfp.dut.scatter[i].scatter_interface.barrier:
						num_visited += 1
						print("Visiting " + str(selfp.dut.scatter[i].scatter_interface.msg) + " (level " + str(selfp.dut.apply[i].level) + ")")
			yield

		if num_visited < num_nodes:
			print("Only {} out of {} nodes visited.".format(num_visited, num_nodes))

		ret = yield from riffa.channel_read(selfp.simulator, self.tx)

		yield 100
		print(ret[0:64:4])

		print(str(selfp.dut.initgraph.cycles_calc) + " cycles taken for algorithm itself.")
		# # verify in-memory spanning tree
		# for pe in range(self.addresslayout.num_pe):
		# 	for adr in range(self.addresslayout.num_nodes_per_pe):
		# 		print("{}: {}".format(self.addresslayout.global_adr(pe, adr), selfp.simulator.rd(self.apply[pe].mem, adr)))

if __name__ == "__main__":
	if len(sys.argv) > 1:
		graphfile = open(sys.argv[1])
	else:
		graphfile = None
	tb = TB(graphfile=graphfile)
	run_simulation(tb, vcd_name="tb.vcd", keep_files=True, ncycles=100000)