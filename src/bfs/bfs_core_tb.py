from migen.fhdl.std import *
from migen.genlib.fifo import SyncFIFO
from migen.genlib.misc import optree

from migen.sim.generic import run_simulation

from bfs_graph_input import read_graph
from bfs_interfaces import BFSApplyInterface, BFSScatterInterface, BFSMessage
from bfs_address import BFSAddressLayout
from bfs_arbiter import BFSArbiter
from bfs_apply import BFSApply
from bfs_scatter import BFSScatter


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

		pcie_width = 128

		if graphfile:
			self.adj_dict = read_graph(graphfile)
		else:
			self.adj_dict = {1:[2,3,4], 2:[1,5,6], 3:[1,4,7], 4:[1,3,5], 5:[2,4,6], 6:[2,5,7], 7:[3,6]}

		self.addresslayout = BFSAddressLayout(nodeidsize, edgeidsize, peidsize, num_pe, num_nodes_per_pe, max_edges_per_pe)

		adj_idx, adj_val = self.addresslayout.generate_partition(self.adj_dict)


		fifos = [[SyncFIFO(width_or_layout=BFSMessage(nodeidsize).layout, depth=128) for _ in range(num_pe)] for _ in range(num_pe)]
		self.submodules.fifos = fifos
		self.submodules.arbiter = [BFSArbiter(self.addresslayout, fifos[sink]) for sink in range(num_pe)]
		self.submodules.apply = [BFSApply(self.addresslayout) for _ in range(num_pe)]
		self.submodules.scatter = [BFSScatter(self.addresslayout, adj_mat=(adj_idx[i], adj_val[i])) for i in range(num_pe)]

		# connect within PEs
		self.comb += [self.arbiter[i].apply_interface.connect(self.apply[i].apply_interface) for i in range(num_pe)],\
					 [self.apply[i].scatter_interface.connect(self.scatter[i].scatter_interface) for i in range(num_pe)]

		# connect fifos across PEs
		for source in range(num_pe):
			array_dest_id = Array(fifo.din.dest_id for fifo in [fifos[sink][source] for sink in range(num_pe)])
			array_parent = Array(fifo.din.parent for fifo in [fifos[sink][source] for sink in range(num_pe)])
			array_barrier = Array(fifo.din.barrier for fifo in [fifos[sink][source] for sink in range(num_pe)])
			array_we = Array(fifo.we for fifo in [fifos[sink][source] for sink in range(num_pe)])
			array_writable = Array(fifo.writable for fifo in [fifos[sink][source] for sink in range(num_pe)])

			have_barrier = Signal()
			barrier_ack = Array(Signal() for _ in range(num_pe))
			barrier_done = Signal()

			self.comb += barrier_done.eq(optree("&", barrier_ack)), have_barrier.eq(self.scatter[source].network_interface.msg.barrier & self.scatter[source].network_interface.valid)

			self.sync += If(have_barrier & ~barrier_done,
							[barrier_ack[i].eq(barrier_ack[i] | array_writable[i]) for i in range(num_pe)]
						 ).Else(
						 	[barrier_ack[i].eq(0) for i in range(num_pe)]
						 )

			sink = Signal(self.addresslayout.peidsize)

			self.comb+= If(have_barrier,
							[array_barrier[i].eq(1) for i in range(num_pe)],
							[array_we[i].eq(~barrier_ack[i]) for i in range(num_pe)],
							self.scatter[source].network_interface.ack.eq(barrier_done)
						).Else(
							sink.eq(self.scatter[source].network_interface.dest_pe),\
							array_dest_id[sink].eq(self.scatter[source].network_interface.msg.dest_id),\
							array_parent[sink].eq(self.scatter[source].network_interface.msg.parent),\
							array_we[sink].eq(self.scatter[source].network_interface.valid),\
							self.scatter[source].network_interface.ack.eq(array_writable[sink])
						)

		# state of calculation
		self.global_inactive = Signal()
		self.comb += self.global_inactive.eq(optree("&", [pe.inactive for pe in self.apply]))

	def gen_simulation(self, selfp):
		num_pe = self.addresslayout.num_pe

		init_node = 1
		init_node_pe = 0

		start_message = [selfp.arbiter[i].start_message for i in range(num_pe)]
		start_message[init_node_pe].msg.dest_id = init_node
		start_message[init_node_pe].msg.parent = init_node
		start_message[init_node_pe].msg.barrier = 0
		start_message[init_node_pe].valid = 1

		while start_message[init_node_pe].ack==0:
			yield
		start_message[init_node_pe].valid = 0

		for i in range(num_pe):
			start_message[i].msg.dest_id = 0
			start_message[i].msg.parent = 0
			start_message[i].msg.barrier = 1
			start_message[i].valid = 1

		barrier_done = [0 for i in range(num_pe)]
		
		while 0 in barrier_done:
			yield
			for i in range(num_pe):
				if start_message[i].ack:
					start_message[i].valid = 0
					barrier_done[i] = 1

		num_visited = 0
		num_nodes = len(self.adj_dict)
		while selfp.global_inactive==0:
			for i in range(self.addresslayout.num_pe):
				if selfp.scatter[i].scatter_interface.valid & selfp.scatter[i].scatter_interface.ack:
					if not selfp.scatter[i].scatter_interface.barrier:
						num_visited += 1
						# print("Visiting " + str(selfp.scatter[i].scatter_interface.msg) + " (level " + str(selfp.apply[i].level) + ")")
			yield

		if num_visited < num_nodes:
			print("Only {} out of {} nodes visited.".format(num_visited, num_nodes))
		else:
			print("Successfully visited all nodes.")

		print(str(selfp.simulator.cycle_counter) + " cycles taken.")

if __name__ == "__main__":
	if len(sys.argv) > 1:
		graphfile = open(sys.argv[1])
	else:
		graphfile = None
	tb = TB(graphfile=graphfile)
	run_simulation(tb, vcd_name="tb.vcd", keep_files=True, ncycles=100000)