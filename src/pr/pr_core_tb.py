"""Simulate PR grid"""

from migen.fhdl.std import *
from migen.genlib.fifo import SyncFIFO
from migen.genlib.misc import optree

from migen.sim.generic import *

from pr_graph_input import read_graph
from pr_graph_generate import generate_graph
from pr_interfaces import PRMessage
from pr_address import PRAddressLayout
from pr_arbiter import PRArbiter
from pr_apply import PRApply
from pr_scatter import PRScatter
from pr_config import config


import riffa

import sys
import argparse
import random, struct

def _float_to_32b_int(f):
	return struct.unpack("i", struct.pack("f", f))[0]

def _32b_int_to_float(i):
	return struct.unpack("f", struct.pack("i", i))[0]


class UpdateMonitor(Module):
	def __init__(self, applys):
		self.apply = applys

	def gen_simulation(self, selfp):
		num_pe = len(self.apply)
		while True:
			for i in range(num_pe):
				if selfp.apply[i].applykernel.message_valid & selfp.apply[i].outfifo.we:
					print("Node " + str(selfp.apply[i].applykernel.message_sender) + " updated in round " + str(selfp.apply[i].level) +". New weight: " + str(selfp.apply[i].applykernel.message_out.weight))
			yield

	gen_simulation.passive = True

class TB(Module):
	def __init__(self, adj_dict):

		self.addresslayout = config()

		num_pe = self.addresslayout.num_pe
		num_nodes_per_pe = self.addresslayout.num_nodes_per_pe

		self.adj_dict = adj_dict
		num_nodes = len(adj_dict)
		self.addresslayout.const_base = _float_to_32b_int(0.15/num_nodes)

		adj_idx, adj_val = self.addresslayout.generate_partition(self.adj_dict)
		init_nodedata = [0] + [len(self.adj_dict[node]) for node in range(1, num_nodes+1)] + [0 for _ in range(num_nodes+1, num_pe*num_nodes_per_pe)]


		fifos = [[SyncFIFO(width_or_layout=PRMessage(**self.addresslayout.get_params()).layout, depth=128) for _ in range(num_pe)] for _ in range(num_pe)]
		self.submodules.fifos = fifos
		self.submodules.arbiter = [PRArbiter(self.addresslayout, fifos[sink]) for sink in range(num_pe)]
		self.submodules.apply = [PRApply(self.addresslayout, init_nodedata[num_nodes_per_pe*i:num_nodes_per_pe*(i+1)]) for i in range(num_pe)]
		self.submodules.scatter = [PRScatter(self.addresslayout, adj_mat=(adj_idx[i], adj_val[i])) for i in range(num_pe)]

		# connect within PEs
		self.comb += [self.arbiter[i].apply_interface.connect(self.apply[i].apply_interface) for i in range(num_pe)],\
					 [self.apply[i].scatter_interface.connect(self.scatter[i].scatter_interface) for i in range(num_pe)]

		# connect fifos across PEs
		for source in range(num_pe):
			array_dest_id = Array(fifo.din.dest_id for fifo in [fifos[sink][source] for sink in range(num_pe)])
			array_parent = Array(fifo.din.payload for fifo in [fifos[sink][source] for sink in range(num_pe)])
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
							array_parent[sink].eq(self.scatter[source].network_interface.msg.payload),\
							array_we[sink].eq(self.scatter[source].network_interface.valid),\
							self.scatter[source].network_interface.ack.eq(array_writable[sink])
						)

		# state of calculation
		self.global_inactive = Signal()
		self.comb += self.global_inactive.eq(optree("&", [pe.inactive for pe in self.apply]))

		self.submodules += UpdateMonitor(self.apply)

	def gen_simulation(self, selfp):
		num_pe = self.addresslayout.num_pe
		num_nodes_per_pe = self.addresslayout.num_nodes_per_pe

		init_messages = {}
		for node in self.adj_dict:
			pe = node >> log2_int(num_nodes_per_pe)
			if pe not in init_messages:
				init_messages[pe] = []
			init_messages[pe].append((node, self.addresslayout.const_base))

		print(init_messages)

		start_message = [selfp.arbiter[i].start_message for i in range(num_pe)]

		for i in range(num_pe):
			start_message[i].select = 1
			start_message[i].valid = 0

		while init_messages:
			for i in range(num_pe):
				if start_message[i].ack:
					if i in init_messages:
						node, message = init_messages[i].pop()
						start_message[i].msg.dest_id = node
						start_message[i].msg.payload = message
						start_message[i].msg.barrier = 0
						start_message[i].valid = 1
						if len(init_messages[i]) == 0:
							del init_messages[i]
					else:
						start_message[i].valid = 0
			yield

		for i in range(num_pe):
			start_message[i].msg.dest_id = 0
			start_message[i].msg.payload = 0
			start_message[i].msg.barrier = 1
			start_message[i].valid = 1

		barrier_done = [0 for i in range(num_pe)]
		
		while 0 in barrier_done:
			yield
			for i in range(num_pe):
				if start_message[i].ack:
					start_message[i].valid = 0
					barrier_done[i] = 1

		for i in range(num_pe):
			start_message[i].select = 0

		while selfp.global_inactive==0:
			yield

		print(str(selfp.simulator.cycle_counter) + " cycles taken.")

if __name__ == "__main__":
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument('-f', '--from-file', dest='graphfile',
                        help='filename containing graph')
	parser.add_argument('-n', '--nodes', type=int,
						help='number of nodes to generate')
	parser.add_argument('-e', '--edges', type=int,
						help='number of edges to generate')
	parser.add_argument('-s', '--seed', type=int,
						help='seed to initialise random number generator')
	parser.add_argument('--random-walk', action='store_const',
						const='random_walk', dest='approach',
						help='use a random-walk generation algorithm (default)')
	parser.add_argument('--naive', action='store_const',
						const='naive', dest='approach',
						help='use a naive generation algorithm (slower)')
	parser.add_argument('--partition', action='store_const',
						const='partition', dest='approach',
						help='use a partition-based generation algorithm (biased)')
	args = parser.parse_args()

	if args.graphfile:
		graphfile = open(args.graphfile)
		adj_dict = read_graph(graphfile)
	elif args.nodes:
		if args.seed:
			s = args.seed
		else:
			s = 42
		random.seed(s)
		num_nodes = args.nodes
		if args.edges:
			num_edges = args.edges
		else:
			num_edges = num_nodes-1
		if args.approach:
			approach = args.approach
		else:
			approach = "random_walk"
		adj_dict = generate_graph(num_nodes, num_edges, approach=approach)
	else:
		parser.print_help()
		exit(-1)

	tb = TB(adj_dict)
	# run_simulation(tb, vcd_name="tb.vcd", keep_files=True, ncycles=200000)
	with Simulator(tb, TopLevel("tb.vcd"), icarus.Runner(keep_files=True), display_run=True) as s:
		s.run(20000)