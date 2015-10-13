from migen.fhdl.std import *
from migen.sim.generic import run_simulation

from pr_scatterkernel import PRScatterKernel
from pr_config import config
from pr_graph_generate import generate_graph

import random, struct

def _float_to_32b_int(f):
	return struct.unpack("i", struct.pack("f", f))[0]

def _32b_int_to_float(i):
	return struct.unpack("f", struct.pack("i", i))[0]

class MessageReader(Module):
	def __init__(self, sk):
		self.sk = sk
		self.msgs = []

	def gen_simulation(self, selfp):
		while True:
			selfp.sk.message_ack = random.choice([0,1])
			if selfp.sk.message_ack:
				if selfp.sk.barrier_out:
					print("Barrier")
				elif selfp.sk.valid_out:
					print("Message: ({}, {})".format(selfp.sk.neighbor_out, _32b_int_to_float(selfp.sk.message_out.weight)))
					self.msgs.append((selfp.sk.neighbor_out, selfp.sk.message_out.weight))
			yield

	gen_simulation.passive = True

class TB(Module):
	def __init__(self):
		self.addresslayout = config()

		num_nodes = self.addresslayout.num_nodes_per_pe - 1

		self.graph = generate_graph(num_nodes=num_nodes, num_edges=2*num_nodes)

		print(self.graph)

		self.submodules.dut = PRScatterKernel(self.addresslayout)
		self.submodules.msgreader = MessageReader(self.dut)

	def gen_simulation(self, selfp):
		num_nodes = len(self.graph)

		msg = [(i, _float_to_32b_int(random.random())) for j in range(1, num_nodes+1) for i in self.graph[j]]
		random.shuffle(msg)

		print("Input messages: " + str(msg))

		print("Received output:")

		while msg:
			node, weight = msg.pop(0)
			selfp.dut.message_in.weight = weight
			selfp.dut.num_neighbors_in = len(self.graph[node])
			selfp.dut.neighbor_in = node
			selfp.dut.barrier_in = 0
			selfp.dut.valid_in = 1
			yield
			while not selfp.dut.valid_in & selfp.dut.ready:
				yield
		selfp.dut.valid_in = 0

		yield 110

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
