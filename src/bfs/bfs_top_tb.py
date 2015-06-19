from migen.fhdl.std import *

from migen.sim.generic import run_simulation

from bfs_top import BFS
from bfs_address import BFSAddressLayout

import riffa

class TB(Module):
	def __init__(self):
		nodeidsize = 8
		num_nodes_per_pe = 2**2
		edgeidsize = 8
		max_edges_per_pe = 2**4
		peidsize = 1
		num_pe = 2

		pcie_width = 128

		self.addresslayout = BFSAddressLayout(nodeidsize, edgeidsize, peidsize, num_pe, num_nodes_per_pe, max_edges_per_pe, pcie_width)

		self.rx = riffa.Interface(data_width=pcie_width)
		self.tx = riffa.Interface(data_width=pcie_width)
		dummy_rx = Signal()
		dummy_tx = Signal()
		self.comb += dummy_rx.eq(self.rx.raw_bits()), dummy_tx.eq(self.tx.raw_bits())

		self.submodules.dut = BFS(self.addresslayout, self.rx, self.tx)

	def gen_simulation(self, selfp):
		adj_dict = {1:[2,3,4], 2:[1,5,6], 3:[1,4,7], 4:[1,3,5], 5:[2,4,6], 6:[2,5,7], 7:[3,6]}
		adj_idx, adj_val = self.addresslayout.generate_partition(adj_dict)
		print("adj_idx: " + str([hex(x) for x in adj_idx]))
		print("adj_val: " + str(adj_val))
		adj_idx_flat = self.addresslayout.repack(adj_idx, 2*self.addresslayout.edgeidsize, self.addresslayout.pcie_width)
		adj_val_flat = self.addresslayout.repack(adj_val, self.addresslayout.nodeidsize, self.addresslayout.pcie_width)
		print("adj_idx_flat: " + str([hex(x) for x in adj_idx_flat]))
		print("adj_val_flat: " + str([hex(x) for x in adj_val_flat]))

		yield from riffa.channel_write(selfp.simulator, self.rx, adj_idx_flat)
		yield from riffa.channel_write(selfp.simulator, self.rx, adj_val_flat)

		# check nodes are visited
		num_visited = 0
		num_nodes = 7
		while num_visited < num_nodes:
			for i in range(self.addresslayout.num_pe):
				if selfp.dut.scatter[i].scatter_interface.valid & selfp.dut.scatter[i].scatter_interface.ack:
					if not selfp.dut.scatter[i].scatter_interface.barrier:
						num_visited += 1
						print("Visiting " + str(selfp.dut.scatter[i].scatter_interface.msg) + " (level " + str(selfp.dut.apply[i].level) + ")")
			yield
		yield 100

		# verify in-memory spanning tree
		for pe in range(self.addresslayout.num_pe):
			for adr in range(self.addresslayout.num_nodes_per_pe):
				print("{}: {}".format(self.addresslayout.global_adr(pe, adr), selfp.simulator.rd(self.dut.apply[pe].mem, adr)))


if __name__ == "__main__":
	tb = TB()
	run_simulation(tb, vcd_name="tb.vcd", keep_files=True, ncycles=250)