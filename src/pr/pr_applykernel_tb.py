from migen.fhdl.std import *
from migen.sim.generic import *

from pr_applykernel import PRApplyKernel
from pr_address import PRAddressLayout
from pr_config import config
from pr_graph_generate import generate_graph
import random
import struct 

def _float_to_32b_int(f):
	return struct.unpack("i", struct.pack("f", f))[0]

def _32b_int_to_float(i):
	return struct.unpack("f", struct.pack("i", i))[0]

class MessageReader(Module):
	def __init__(self, num_nodes, message_out, message_sender, message_valid, barrier_out, message_ack):
		self.message_out = message_out
		self.message_sender = message_sender
		self.message_valid = message_valid
		self.barrier_out = barrier_out
		self.message_ack = message_ack
		self.num_nodes = num_nodes

	def gen_simulation(self, selfp):
		nrecvd = 0
		while nrecvd < self.num_nodes:
			selfp.message_ack = random.choice([0, 1])
			if selfp.message_ack:
				if selfp.barrier_out:
					print("Barrier")
				elif selfp.message_valid:
					nrecvd = nrecvd + 1
					print("({}, {})".format(selfp.message_sender, _32b_int_to_float(selfp.message_out.weight)))
			yield
		print("Done")




class TB(Module):
	def __init__(self):
		self.addresslayout = config()

		num_nodes = self.addresslayout.num_nodes_per_pe - 1

		self.addresslayout.const_base = _float_to_32b_int(0.15/num_nodes)

		self.graph = generate_graph(num_nodes=num_nodes, num_edges=2*num_nodes)

		init_nodedata = [0] + [len(self.graph[node]) for node in range(1, num_nodes+1)]

		self.submodules.dut = PRApplyKernel(self.addresslayout)
		self.submodules.messagereader = MessageReader(num_nodes=num_nodes,
										message_out=self.dut.message_out,
										message_sender=self.dut.message_sender, 
										message_valid=self.dut.message_valid, 
										barrier_out=self.dut.barrier_out, 
										message_ack=self.dut.message_ack)


	def gen_simulation(self, selfp):
		num_nodes = len(self.graph)

		msg = [(i, _float_to_32b_int(random.random())) for i in range(1, num_nodes+1) for _ in range(len(self.graph[i]))] #(dest_id, weight)
		random.shuffle(msg)
		msg.append(('end', 'end'))
		print("Input messages: " + str(msg))

		expected = [0.0 for i in range(num_nodes + 1)]
		for node, weight in msg[:-1]:
			expected[node] += _32b_int_to_float(weight)

		print("Expected output:")
		for node in range(1, num_nodes + 1):
			expected[node] = 0.15/num_nodes + 0.85*expected[node]
			print("{}: {}".format(node, expected[node]))

		print("Received output:")

		nneighbors = [0] + [len(self.graph[node]) for node in range(1, num_nodes+1)]
		nrecvd = [0 for node in range(num_nodes+1)]
		summ = [0.0 for node in range(num_nodes+1)]

		currently_active = set()

		node, weight = msg.pop(0)

		while msg:
			selfp.dut.level_in = 3
			selfp.dut.nodeid_in = node
			selfp.dut.message_in.weight = weight
			selfp.dut.state_in.nneighbors = nneighbors[node]
			selfp.dut.state_in.nrecvd = nrecvd[node]
			selfp.dut.state_in.sum = summ[node]
			selfp.dut.barrier_in = 0
			if node in currently_active:
				selfp.dut.valid_in = 0
			else:
				selfp.dut.valid_in = 1
				currently_active.add(node)
				node, weight = msg.pop(0)
			yield
			if selfp.dut.state_valid:
					assert(nneighbors[selfp.dut.nodeid_out] == selfp.dut.state_out.nneighbors)
					nrecvd[selfp.dut.nodeid_out] = selfp.dut.state_out.nrecvd
					summ[selfp.dut.nodeid_out] = selfp.dut.state_out.sum
					currently_active.remove(selfp.dut.nodeid_out)
			while not selfp.dut.ready:
				yield
				if selfp.dut.state_valid:
					assert(nneighbors[selfp.dut.nodeid_out] == selfp.dut.state_out.nneighbors)
					nrecvd[selfp.dut.nodeid_out] = selfp.dut.state_out.nrecvd
					summ[selfp.dut.nodeid_out] = selfp.dut.state_out.sum
					currently_active.remove(selfp.dut.nodeid_out)

		selfp.dut.valid_in = 0

	gen_simulation.passive = True
				
if __name__ == "__main__":
	random.seed(42)
	tb = TB()
	#run_simulation(tb, vcd_name="tb.vcd", ncycles=200, keep_files=True)
	with Simulator(tb, TopLevel("tb.vcd"), icarus.Runner(keep_files=True), display_run=False) as s:
		s.run(2000)
	
