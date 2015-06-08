from migen.fhdl.std import *

from migen.sim.generic import run_simulation

from bfs_top import BFS

class TB(Module):
	def __init__(self):
		nodeidsize = 8
		num_nodes_per_pe = 2**4
		max_edges_per_pe = 2**5
		self.num_pe = 2

		adj_idx = [(0,0),(0,3),(3,3),(6,3),(9,3),(12,3),(15,3),(18,2)]
		adj_val = [2,3,4,1,5,6,1,4,7,1,3,5,2,4,6,2,5,7,3,6]

		self.submodules.dut = BFS(self.num_pe, nodeidsize, num_nodes_per_pe, max_edges_per_pe, adj_mat=(adj_idx, adj_val))

	def gen_simulation(self, selfp):
		root = 6
		root_pe = root % self.num_pe
		selfp.dut.arbiter[root_pe].start_message.msg.dest_id = root
		selfp.dut.arbiter[root_pe].start_message.msg.parent = root
		selfp.dut.arbiter[root_pe].start_message.valid = 1
		yield
		while selfp.dut.arbiter[root_pe].start_message.ack == 0:
			yield
		selfp.dut.arbiter[root_pe].start_message.valid = 0
		num_visited = 0
		num_nodes = 7
		while num_visited < num_nodes:
			for i in range(self.num_pe):
				if selfp.dut.scatter[i].scatter_interface.valid & selfp.dut.scatter[i].scatter_interface.ack:
					num_visited += 1
					print("Visiting " + str(selfp.dut.scatter[i].scatter_interface.msg))
			yield
		yield 10


if __name__ == "__main__":
	tb = TB()
	run_simulation(tb, vcd_name="tb.vcd", ncycles=250)