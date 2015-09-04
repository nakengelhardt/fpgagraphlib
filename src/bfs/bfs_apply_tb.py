from migen.fhdl.std import *
from migen.sim.generic import run_simulation

from bfs_apply import BFSApply
from bfs_address import BFSAddressLayout
from bfs_config import config
import random

class TB(Module):
	def __init__(self):
		self.addresslayout = config()

		self.submodules.dut = BFSApply(self.addresslayout)


	def gen_simulation(self, selfp):
		msg = [(6,6), (5,6), (5,6), (2,6), (7,6), (3,7), (6,7), (4,5), (1,2)] #(dest_id, parent)
		msgs_sent = 0

		scatter = []
		selfp.dut.scatter_interface.ack = 0
		yield

		while msgs_sent < len(msg):
			# input
			a, b = msg[msgs_sent]
			selfp.dut.apply_interface.msg.dest_id = a
			selfp.dut.apply_interface.msg.payload = b
			selfp.dut.apply_interface.valid = 1

			# output
			# test pipeline stall: only sometimes ack
			ack = random.choice([0,1])
			selfp.dut.scatter_interface.ack = ack
				
			yield

			# check for input success
			if selfp.dut.apply_interface.ack:
				msgs_sent += 1

			# check for output success
			if selfp.dut.scatter_interface.valid & selfp.dut.scatter_interface.ack:
				scatter.append(selfp.dut.scatter_interface.msg)

		# done sending
		selfp.dut.apply_interface.valid = 0

		# empty the pipeline (3 cycles max latency)
		selfp.dut.scatter_interface.ack = 1
		for i in range(3):
			if selfp.dut.scatter_interface.valid & selfp.dut.scatter_interface.ack:
				scatter.append(selfp.dut.scatter_interface.msg)
			yield

		print("Visit order: " + str(scatter))
		print("Parent data:")
		for i in range(1, self.addresslayout.num_nodes_per_pe):
			print(str(i) + ": " + str(selfp.simulator.rd(self.dut.mem, i)))

				
if __name__ == "__main__":
	tb = TB()
	run_simulation(tb, vcd_name="tb.vcd", ncycles=100)
