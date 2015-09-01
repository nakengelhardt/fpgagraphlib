from migen.fhdl.std import *
from migen.genlib.fifo import SyncFIFO
from migen.sim.generic import run_simulation

from bfs_scatter import BFSScatter
from bfs_address import BFSAddressLayout

class NetReader(Module):
	def __init__(self, net):
		self.net = net

	def gen_simulation(self, selfp):
		selfp.net.ack = 1
		while True:
			if selfp.net.valid:
				print("Message sent to PE " + str(selfp.net.dest_pe) + ": (" + str(selfp.net.msg.dest_id) + ", " + str(selfp.net.msg.payload.parent) + ")")
			yield

	gen_simulation.passive = True


class TB(Module):
	def __init__(self):
		nodeidsize = 8
		num_nodes_per_pe = 2**4
		edgeidsize = 8
		max_edges_per_pe = 2**5
		peidsize = 2
		num_pe = 2
		pcie_width = 128

		self.addresslayout = BFSAddressLayout(nodeidsize=nodeidsize, edgeidsize=edgeidsize, peidsize=peidsize, num_pe=num_pe, num_nodes_per_pe=num_nodes_per_pe, max_edges_per_pe=max_edges_per_pe)

		adj_idx = [(0,0),(0,3),(3,3),(6,3),(9,3),(12,3),(15,3),(18,2)]
		adj_val = [2,3,4,1,5,6,1,4,7,1,3,5,2,4,6,2,5,7,3,6]

		self.submodules.dut = BFSScatter(self.addresslayout, adj_mat=(adj_idx, adj_val))

		self.submodules += NetReader(self.dut.network_interface)
		

	def gen_simulation(self, selfp):
		msg = [6, 5, 2, 7, 3, 4, 1]
		msgs_sent = 0
		while msgs_sent < len(msg):
			selfp.dut.scatter_interface.msg.parent = msg[msgs_sent]
			selfp.dut.scatter_interface.valid = 1
			yield
			if selfp.dut.scatter_interface.ack == 1:	
				msgs_sent += 1
		selfp.dut.scatter_interface.valid = 0

		yield 20

if __name__ == "__main__":
	tb = TB()
	run_simulation(tb, vcd_name="tb.vcd", ncycles=200)

		