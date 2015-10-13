from migen.fhdl.std import *
from migen.genlib.fifo import SyncFIFO
from migen.sim.generic import *

from pr_interfaces import PRMessage
from pr_arbiter import PRArbiter
from pr_address import PRAddressLayout
from pr_config import config

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
				print("Sending message " + str((dest_id, parent)) + " on fifo " + str(pe))
				selfp.fifos[pe].din.dest_id = dest_id
				selfp.fifos[pe].din.payload = parent
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

		self.addresslayout = config()

		num_pe = self.addresslayout.num_pe

		fifos = [SyncFIFO(width_or_layout=PRMessage(**self.addresslayout.get_params()).layout, depth=32) for _ in range(num_pe)]
		self.submodules += fifos

		self.submodules.dut = PRArbiter(self.addresslayout, fifos)

		self.messages = [(1, 171753), (2, 84960), (3, 80667), (4, 78659), (5, 34255), (6, 93813), (7, 132367)]
		
		# delegate input to submodule
		self.submodules += FifoWriter(fifos, self.messages.copy()) # messages modified afterwards!

	def gen_simulation(self, selfp):
		# check output
		# TODO: add testing of pipeline stall by sometimes turning ack off?
		selfp.dut.apply_interface.ack = 1
		selfp.dut.start_message.select = 0
		
		msgs_received = 0
		total_msgs = len(self.messages)
		print("Total messages: " + str(total_msgs))
		while msgs_received < total_msgs:
			if selfp.dut.apply_interface.valid:
				msg = (selfp.dut.apply_interface.msg.dest_id, selfp.dut.apply_interface.msg.payload)
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
	# run_simulation(tb, vcd_name="tb.vcd", ncycles=250)
	with Simulator(tb, TopLevel("tb.vcd"), icarus.Runner(keep_files=True), display_run=True) as s:
		s.run(250)