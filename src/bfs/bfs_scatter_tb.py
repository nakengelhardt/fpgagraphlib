from migen.fhdl.std import *
from migen.genlib.fifo import SyncFIFO
from migen.sim.generic import run_simulation

from bfs_interfaces import BFSMessage
from bfs_scatter import BFSScatter

class FifoReader(Module):
	def __init__(self, fifos):
		self.fifos = fifos

	def gen_simulation(self, selfp):
		while True:
			for i in len(self.fifos):
				if selfp.fifos[i].readable:
					print("Message sent to PE " + str(i) + ": (" + str(selfp.fifos[i].dout.dest_id) + ", " + str(selfp.fifos[i].dout.parent) + ")")
					selfp.fifos[i].re = 1
					yield
					selfp.fifos[i].re = 0

	gen_simulation.passive = True


class TB(Module):
	def __init__(self):
		nodeidsize = 16
		num_nodes_per_pe = 2**8
		max_edges_per_pe = 2**8
		num_pe = 8

		fifos = [SyncFIFO(width_or_layout=BFSMessage(nodeidsize).layout, depth=32) for _ in range(num_pe)]
		self.submodules += fifos

		adj_idx = [(0,0),(0,3),(3,3),(6,3),(9,3),(12,3),(15,3),(18,2)]
		adj_val = [2,3,4,2,5,6,1,4,7,1,3,5,2,4,6,2,5,7,3,6]

		self.submodules.dut = BFSScatter(num_pe, nodeidsize, num_nodes_per_pe, max_edges_per_pe, fifos, adj_mat=(adj_idx,adj_val))

		

	def gen_simulation(self, selfp):
		msg = [6, 5, 2, 7, 3, 4, 1]
		msgs_sent = 0

		while msgs_sent < len(msg):
			selfp.dut.scatter_interface.msg = msg[msgs_sent]
			selfp.dut.scatter_interface.valid = 1
			yield
			if selfp.dut.scatter_interface.ack == 1:	
				msgs_sent += 1
		selfp.dut.scatter_interface.valid = 0

		yield 3

if __name__ == "__main__":
	tb = TB()
	run_simulation(tb, vcd_name="tb.vcd", ncycles=100)