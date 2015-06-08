from migen.fhdl.std import *
from migen.genlib.fifo import SyncFIFO
from migen.sim.generic import run_simulation

from bfs_interfaces import BFSApplyInterface, BFSMessage
from bfs_arbiter import BFSArbiter

class FifoWriter(Module):
	def __init__(self, fifos, messages):
		self.fifos = fifos
		self.messages = messages.copy()

	def gen_simulation(self, selfp):
		msgs_sent = 0
		for i in range(len(self.fifos)):
				selfp.fifos[i].we = 0
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



class TB(Module):
	def __init__(self):
		nodeidsize = 16
		num_nodes_per_pe = 2**8
		max_edges_per_pe = 2**8
		num_pe = 2

		fifos = [SyncFIFO(width_or_layout=BFSMessage(nodeidsize).layout, depth=32) for _ in range(num_pe)]
		self.submodules += fifos

		self.submodules.dut = BFSArbiter(num_pe, nodeidsize, fifos)

		self.messages = [(2, 6), (5, 6), (7, 6), (2, 5), (4, 5), (6, 5), (1, 2), (5, 2), (6, 2), (3, 7), (6, 7), (1, 3), (4, 3), (7, 3), (1, 4), (3, 4), (5, 4), (2, 1), (3, 1)]
		
		self.submodules += FifoWriter(fifos, self.messages)

	def gen_simulation(self, selfp):
		selfp.dut.apply_interface.ack = 1
		msgs_received = 0
		total_msgs = len(self.messages)
		print("Total messages: " + str(total_msgs))
		while msgs_received < total_msgs:
			if selfp.dut.apply_interface.valid:
				msg = (selfp.dut.apply_interface.msg.dest_id, selfp.dut.apply_interface.msg.parent)
				txt = str(msgs_received) + " Message received: " + str(msg)
				try:
					self.messages.remove(msg)
					msgs_received += 1
				except ValueError as e:
					txt += " ! unexpected"
				print(txt)
			yield
		if self.messages:
			print("Messages not received: " + str(self.messages))


if __name__ == "__main__":
	tb = TB()
	run_simulation(tb, vcd_name="tb.vcd", ncycles=250)