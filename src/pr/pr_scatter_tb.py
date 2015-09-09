from migen.fhdl.std import *
from migen.genlib.fifo import SyncFIFO
from migen.sim.generic import run_simulation

from pr_scatter import PRScatter
from pr_address import PRAddressLayout
from pr_config import config

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

		adj_idx = [(0,0),(0,3),(3,3),(6,3),(9,3),(12,3),(15,3),(18,2)]
		adj_val = [2,3,4,1,5,6,1,4,7,1,3,5,2,4,6,2,5,7,3,6]

		self.submodules.dut = PRScatter(self.addresslayout, adj_mat=(adj_idx, adj_val))

		self.submodules += NetReader(self.dut.network_interface)
		

	def gen_simulation(self, selfp):
		msg = [(1, 171753), (2, 84960), (3, 80667), (4, 78659), (5, 34255), (6, 93813), (7, 132367)]
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
	tb = TB()
	run_simulation(tb, vcd_name="tb.vcd", ncycles=200)

		