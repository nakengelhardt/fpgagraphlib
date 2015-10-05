from migen.fhdl.std import *
from migen.sim.generic import *

from pr_apply import PRApply
from pr_address import PRAddressLayout
from pr_config import config
from pr_graph_generate import generate_graph
from random import random, shuffle, choice, seed
import struct

def _float_to_32b_int(f):
	return struct.unpack("i", struct.pack("f", f))[0]

def _32b_int_to_float(i):
	return struct.unpack("f", struct.pack("i", i))[0]

class ApplyKernelLog(Module):
	def __init__(self, applykernel):
		self.applykernel = applykernel

	def gen_simulation(self, selfp):
		while True:
			yield
			if selfp.applykernel.ready:
				if selfp.applykernel.barrier_in:
					print("Applykernel: barrier in")
				elif selfp.applykernel.valid_in:
					print("Applykernel: message in = nodeid: {}, weight: {}, level: {}\n    associated state in = nneighbors: {}, nrecvd: {}, sum:{}".format(selfp.applykernel.nodeid_in, _32b_int_to_float(selfp.applykernel.message_in.weight), selfp.applykernel.level_in, selfp.applykernel.state_in.nneighbors, selfp.applykernel.state_in.nrecvd, _32b_int_to_float(selfp.applykernel.state_in.sum)))
			if selfp.applykernel.state_valid:
				print("Applykernel: state out = nodeid: {}, nneighbors: {}, nrecvd: {}, sum:{}".format(selfp.applykernel.nodeid_out, selfp.applykernel.state_out.nneighbors, selfp.applykernel.state_out.nrecvd, _32b_int_to_float(selfp.applykernel.state_out.sum)))
			if selfp.applykernel.message_ack:
				if selfp.applykernel.barrier_out:
					print("Applykernel: barrier out")
				elif selfp.applykernel.message_valid:
					print("Applykernel: message out = sender: {}, weight: {}".format(selfp.applykernel.message_sender, _32b_int_to_float(selfp.applykernel.message_out.weight)))
			
	gen_simulation.passive = True

class ScatterInterfaceReader(Module):
	def __init__(self, scatter_interface):
		self.scatter_interface = scatter_interface

	def gen_simulation(self, selfp):
		while True:
			# output
			# test pipeline stall: only sometimes ack
			ack = 1 #choice([0,1])
			selfp.scatter_interface.ack = ack
			yield
			if selfp.scatter_interface.valid & selfp.scatter_interface.ack:
				if selfp.scatter_interface.barrier:
					print("ScatterInterface: barrier")
				else:
					print("ScatterInterface: message = sender: {}, weight: {}".format(selfp.scatter_interface.sender, _32b_int_to_float(selfp.scatter_interface.msg)))

	gen_simulation.passive = True

class TB(Module):
	def __init__(self):
		self.addresslayout = config()

		num_nodes = self.addresslayout.num_nodes_per_pe - 1

		self.addresslayout.const_base = _float_to_32b_int(0.15/num_nodes)

		self.graph = generate_graph(num_nodes=num_nodes, num_edges=2*num_nodes)

		init_nodedata = [0] + [len(self.graph[node]) for node in range(1, num_nodes+1)]

		self.submodules.dut = PRApply(self.addresslayout, init_nodedata=init_nodedata)

		self.submodules += [
			ApplyKernelLog(self.dut.applykernel),
			ScatterInterfaceReader(self.dut.scatter_interface)
		]

	def gen_simulation(self, selfp):
		num_nodes = len(self.graph)

		msg = [(i, _float_to_32b_int(random())) for i in range(1, num_nodes+1) for _ in range(len(self.graph[i]))] #(dest_id, weight)

		print("Input messages: " + str(msg))

		expected = [0.0 for i in range(num_nodes + 1)]
		for node, weight in msg:
			expected[node] += _32b_int_to_float(weight)

		print("Expected output: ")
		for node in range(1, num_nodes + 1):
			expected[node] = 0.15/num_nodes + 0.85*expected[node]
			print("{}: {}".format(node, expected[node]))

		
		selfp.dut.scatter_interface.ack = 0
		yield

		# increase level to 1
		selfp.dut.apply_interface.msg.barrier = 1
		selfp.dut.apply_interface.valid = 1
		selfp.dut.scatter_interface.ack = 1
		yield

		for test in range(4): 
			# missing : test init
			# run 1: send one by one to avoid collisions
			# run 2: send all at once to test collision handling
			# run 3: shuffle messages
			# run 4: increase level past 30, check no more messages sent

			print("### starting run " + str(test) + " ###")

			if test == 2:
				shuffle(msg)

			# raise level to test cutoff
			if test == 3:
				selfp.dut.apply_interface.msg.barrier = 1
				selfp.dut.apply_interface.valid = 1
				while selfp.dut.level < 30:
					yield

			msgs_sent = 0
			scatter = []
			while msgs_sent < len(msg):
				# input
				a, b = msg[msgs_sent]
				selfp.dut.apply_interface.msg.dest_id = a
				selfp.dut.apply_interface.msg.payload = b
				selfp.dut.apply_interface.msg.barrier = 0
				selfp.dut.apply_interface.valid = 1
				yield

				# check for input success
				if selfp.dut.apply_interface.ack:
					msgs_sent += 1
					if test==0:
						selfp.dut.apply_interface.valid = 0
						yield 20

			selfp.dut.apply_interface.msg.barrier = 1
			selfp.dut.apply_interface.valid = 1
			yield
			while not selfp.dut.apply_interface.ack:
				yield
			

			# done sending
			selfp.dut.apply_interface.valid = 0


if __name__ == "__main__":
	s = 42
	seed(s)
	print("Random seed: " + str(s))
	tb = TB()
	#run_simulation(tb, vcd_name="tb.vcd", ncycles=200, keep_files=True)
	with Simulator(tb, TopLevel("tb.vcd"), icarus.Runner(keep_files=True), display_run=False) as s:
		s.run(20000)
	
