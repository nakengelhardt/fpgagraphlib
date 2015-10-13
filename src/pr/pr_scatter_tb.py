from migen.fhdl.std import *
from migen.genlib.fifo import SyncFIFO
from migen.sim.generic import run_simulation

from pr_scatter import PRScatter
from pr_address import PRAddressLayout
from pr_config import config
from pr_graph_generate import generate_graph

import random, struct

def _float_to_32b_int(f):
	return struct.unpack("i", struct.pack("f", f))[0]

def _32b_int_to_float(i):
	return struct.unpack("f", struct.pack("i", i))[0]

class NetReader(Module):
	def __init__(self, net):
		self.net = net

	def gen_simulation(self, selfp):
		selfp.net.ack = 1
		while True:
			if selfp.net.valid:
				print("Message sent to PE " + str(selfp.net.dest_pe) + ": (" + str(selfp.net.msg.dest_id) + ", " + str(selfp.net.msg.payload) + ")")
			yield

	gen_simulation.passive = True


class TB(Module):
	def __init__(self):

		self.addresslayout = config()

		num_nodes = self.addresslayout.num_nodes_per_pe - 1

		self.graph = generate_graph(num_nodes=num_nodes, num_edges=2*num_nodes)
		print(self.graph)

		adj_idx, adj_val = self.addresslayout.generate_partition(self.graph)

		self.submodules.dut = PRScatter(self.addresslayout, adj_mat=(adj_idx[0], adj_val[0]))

		self.submodules += NetReader(self.dut.network_interface)
		

	def gen_simulation(self, selfp):
		num_nodes = len(self.graph)

		msg = [(i, _float_to_32b_int(random.random())) for j in range(1, num_nodes+1) for i in self.graph[j]]
		random.shuffle(msg)

		print("Input messages: " + str(msg))

		msgs_sent = 0
		while msgs_sent < len(msg):
			sender, message = msg[msgs_sent]
			selfp.dut.scatter_interface.msg = message
			selfp.dut.scatter_interface.sender = sender
			selfp.dut.scatter_interface.valid = 1
			yield
			if selfp.dut.scatter_interface.ack == 1:	
				msgs_sent += 1
		selfp.dut.scatter_interface.valid = 0

		yield 20

		# for i in range(1, self.addresslayout.num_nodes_per_pe):
		# 	print(str(i) + ": " + str(selfp.simulator.rd(self.dut.mem_idx, i)))

if __name__ == "__main__":
	try:
		import sys
		s = int(sys.argv[1])
	except Exception as e:
		s = 42
	random.seed(s)
	print("Random seed: " + str(s))
	tb = TB()
	run_simulation(tb, vcd_name="tb.vcd", ncycles=200, keep_files=True)

		