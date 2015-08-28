from migen.fhdl.std import *
from migen.genlib.fifo import SyncFIFO
from migen.sim.generic import run_simulation

from bfs_interfaces import BFSMessage
from bfs_arbiter import BFSArbiter
from bfs_address import BFSAddressLayout

class FifoWriter(Module):
	def __init__(self, fifos, messages):
		self.fifos = fifos
		self.messages = messages 

	def gen_simulation(self, selfp):
		# send inputs
		msgs_sent = 0
		for i in range(len(self.fifos)):
				selfp.fifos[i].we = 0
				selfp.fifos[i].din.barrier = 0
		while msgs_sent < len(self.messages):
			dest_id, parent = self.messages[msgs_sent]
			pe = dest_id % len(self.fifos)
			if selfp.fifos[pe].writable:
				# print("Sending message " + str((dest_id, parent)) + " on fifo " + str(pe))
				selfp.fifos[pe].din.dest_id = dest_id
				selfp.fifos[pe].din.parent = parent
				selfp.fifos[pe].we = 1
				msgs_sent += 1
			yield
			for i in range(len(self.fifos)):
				selfp.fifos[i].we = 0
		yield
		for i in range(len(self.fifos)):
				selfp.fifos[i].we = 1
				selfp.fifos[i].din.barrier = 1
		yield
		for i in range(len(self.fifos)):
				selfp.fifos[i].we = 0
				selfp.fifos[i].din.barrier = 0



class TB(Module):
	def __init__(self):
		nodeidsize = 8
		num_nodes_per_pe = 2**4
		edgeidsize = 8
		max_edges_per_pe = 2**4
		peidsize = 2
		num_pe = 2
		pcie_width = 128

		self.addresslayout = BFSAddressLayout(nodeidsize, edgeidsize, peidsize, num_pe, num_nodes_per_pe, max_edges_per_pe, pcie_width)


		fifos = [SyncFIFO(width_or_layout=BFSMessage(nodeidsize=nodeidsize).layout, depth=32) for _ in range(num_pe)]
		self.submodules += fifos

		self.submodules.dut = BFSArbiter(self.addresslayout, fifos)

		self.messages = [(2, 6), (5, 6), (7, 6), (2, 5), (4, 5), (6, 5), (1, 2), (5, 2), (6, 2), (3, 7), (6, 7), (1, 3), (4, 3), (7, 3), (1, 4), (3, 4), (5, 4), (2, 1), (3, 1)]
		
		# delegate input to submodule
		self.submodules += FifoWriter(fifos, self.messages.copy()) # messages modified afterwards!

	def gen_simulation(self, selfp):
		# check output
		# TODO: add testing of pipeline stall by sometimes turning ack off?
		selfp.dut.apply_interface.ack = 1
		msgs_received = 0
		total_msgs = len(self.messages)
		print("Total messages: " + str(total_msgs))
		while msgs_received < total_msgs:
			if selfp.dut.apply_interface.valid:
				msg = (selfp.dut.apply_interface.msg.dest_id, selfp.dut.apply_interface.msg.parent)
				txt = "{0:{1}d}: ".format(msgs_received, len(str(total_msgs-1))) + str(msg)
				try:
					self.messages.remove(msg)
					msgs_received += 1
				except ValueError as e:
					txt += " ! unexpected"
				print(txt)
			yield
		if self.messages:
			print("Messages not received: " + str(self.messages))
		else:
			print("All messages received.")
		if selfp.dut.apply_interface.valid & selfp.dut.apply_interface.msg.barrier:
			print("Barrier reached.")

if __name__ == "__main__":
	tb = TB()
	run_simulation(tb, vcd_name="tb.vcd", ncycles=250)