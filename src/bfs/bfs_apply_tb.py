from migen.fhdl.std import *
from migen.sim.generic import run_simulation

from bfs_apply import BFSApply


class TB(Module):
	def __init__(self):
		nodeidsize = 16
		num_nodes_per_pe = 2**8

		self.submodules.dut = BFSApply(nodeidsize, num_nodes_per_pe)


	def gen_simulation(self, selfp):
		msg = [(6,6), (5,6), (2,6), (7,6), (3,7), (6,7), (4,5), (1,2)]
		msgs_sent = 0

		scatter = []
		selfp.dut.scatter_interface.ready = 1
		yield

		while msgs_sent < len(msg):
			a, b = msg[msgs_sent]
			selfp.dut.apply_interface.msg.dest_id = a
			selfp.dut.apply_interface.msg.parent = b
			selfp.dut.apply_interface.we = 1
			if selfp.dut.apply_interface.ready:
				msgs_sent += 1

			if selfp.dut.scatter_interface.we:
				scatter.append(selfp.dut.scatter_interface.msg)

			yield

		selfp.dut.apply_interface.we = 0

		for i in range(3):
			if selfp.dut.scatter_interface.we:
				scatter.append(selfp.dut.scatter_interface.msg)

			yield

		print("Visit order: " + str(scatter))
		print("Parent data:")
		for i in range(1,8):
			print(str(i) + ": " + str(selfp.simulator.rd(self.dut.mem, i)))

				
if __name__ == "__main__":
	tb = TB()
	run_simulation(tb, vcd_name="tb.vcd", ncycles=100)
