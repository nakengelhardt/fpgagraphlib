from migen.fhdl.std import *
from migen.sim.generic import run_simulation

from pr_apply import PRApply
from pr_address import PRAddressLayout
from pr_config import config
from pr_graph_generate import generate_graph
from random import random, shuffle, choice

class TB(Module):
	def __init__(self):
		self.addresslayout = config()
		fixedptdecimals = self.addresslayout.fixedptdecimals

		num_nodes = self.addresslayout.num_nodes_per_pe - 1

		self.addresslayout.const_base = int(0.15 / num_nodes * (2**fixedptdecimals))

		self.graph = generate_graph(num_nodes=num_nodes, num_edges=2*num_nodes)

		init_nodedata = [0] + [len(self.graph[node]) for node in range(1, num_nodes+1)]

		self.submodules.dut = PRApply(self.addresslayout, init_nodedata=init_nodedata)


	def gen_simulation(self, selfp):
		fixedptdecimals = self.addresslayout.fixedptdecimals
		num_nodes = len(self.graph)

		msg = [(i, int(random()*(2**fixedptdecimals))) for i in range(1, num_nodes+1) for _ in range(len(self.graph[i]))] #(dest_id, weight)
		shuffle(msg)
		# print("Input messages: " + str(msg))
		
		selfp.dut.scatter_interface.ack = 0
		yield

		# increase level to 1
		selfp.dut.apply_interface.msg.barrier = 1
		selfp.dut.apply_interface.valid = 1
		selfp.dut.scatter_interface.ack = 1
		yield

		for _ in range(2): # test cutoff: send once, increase level to 30, send again

			msgs_sent = 0
			scatter = []
			while msgs_sent < len(msg):
				# input
				a, b = msg[msgs_sent]
				selfp.dut.apply_interface.msg.dest_id = a
				selfp.dut.apply_interface.msg.payload = b
				selfp.dut.apply_interface.msg.barrier = 0
				selfp.dut.apply_interface.valid = 1

				# output
				# test pipeline stall: only sometimes ack
				ack = choice([0,1])
				selfp.dut.scatter_interface.ack = ack
					
				yield

				# check for input success
				if selfp.dut.apply_interface.ack:
					msgs_sent += 1

				# check for output success
				if selfp.dut.scatter_interface.valid & selfp.dut.scatter_interface.ack:
					if selfp.dut.scatter_interface.barrier:
						print("Barrier")
					else:
						scatter.append((selfp.dut.scatter_interface.sender, selfp.dut.scatter_interface.msg))

			selfp.dut.apply_interface.msg.barrier = 1
			selfp.dut.apply_interface.valid = 1
			yield

			# done sending
			selfp.dut.apply_interface.valid = 0

			# empty the pipeline (3 cycles max latency)
			selfp.dut.scatter_interface.ack = 1
			for i in range(5):
				if selfp.dut.scatter_interface.valid & selfp.dut.scatter_interface.ack:
					if selfp.dut.scatter_interface.barrier:
						print("Barrier")
					else:
						scatter.append((selfp.dut.scatter_interface.sender, selfp.dut.scatter_interface.msg))
				yield

			# raise level to test cutoff
			selfp.dut.apply_interface.msg.barrier = 1
			selfp.dut.apply_interface.valid = 1
			selfp.dut.scatter_interface.ack = 1
			while selfp.dut.level < 30:
				yield

			print("Raw: " + str(scatter))

			print("Rank: " + str([float(x)/(2**fixedptdecimals) for _,x in scatter]))
			
		print("Node data:")
		for i in range(1, self.addresslayout.num_nodes_per_pe):
			print(str(i) + ": " + str(selfp.simulator.rd(self.dut.mem, i)))

				
if __name__ == "__main__":
	tb = TB()
	run_simulation(tb, vcd_name="tb.vcd", ncycles=200)
