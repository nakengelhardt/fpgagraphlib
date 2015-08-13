from migen.fhdl.std import *
from migen.genlib.fifo import SyncFIFO
from migen.genlib.misc import optree
from migen.fhdl import verilog

import riffa
from bfs_interfaces import BFSApplyInterface, BFSScatterInterface, BFSMessage
from bfs_arbiter import BFSArbiter
from bfs_apply import BFSApply
from bfs_scatter import BFSScatter
from bfs_address import BFSAddressLayout
from bfs_initgraph import BFSInitGraph

class BFS(Module):
	def __init__(self, addresslayout, rx, tx, adj_mat=None, init_node=6):
		self.addresslayout = addresslayout
		nodeidsize = addresslayout.nodeidsize
		num_nodes_per_pe = addresslayout.num_nodes_per_pe
		num_pe = addresslayout.num_pe
		max_edges_per_pe = addresslayout.max_edges_per_pe

		fifos = [[SyncFIFO(width_or_layout=BFSMessage(nodeidsize).layout, depth=1024) for _ in range(num_pe)] for _ in range(num_pe)]
		self.submodules.fifos = fifos
		self.submodules.arbiter = [BFSArbiter(addresslayout, fifos[sink]) for sink in range(num_pe)]
		self.submodules.apply = [BFSApply(addresslayout) for _ in range(num_pe)]
		self.submodules.scatter = [BFSScatter(addresslayout) for i in range(num_pe)]

		# connect within PEs
		self.comb += [self.arbiter[i].apply_interface.connect(self.apply[i].apply_interface) for i in range(num_pe)],\
					 [self.apply[i].scatter_interface.connect(self.scatter[i].scatter_interface) for i in range(num_pe)]

		# connect fifos across PEs
		for source in range(num_pe):
			array_dest_id = Array(fifo.din.dest_id for fifo in [fifos[sink][source] for sink in range(num_pe)])
			array_parent = Array(fifo.din.parent for fifo in [fifos[sink][source] for sink in range(num_pe)])
			array_barrier = Array(fifo.din.barrier for fifo in [fifos[sink][source] for sink in range(num_pe)])
			array_we = Array(fifo.we for fifo in [fifos[sink][source] for sink in range(num_pe)])
			array_writable = Array(fifo.writable for fifo in [fifos[sink][source] for sink in range(num_pe)])

			have_barrier = Signal()
			barrier_ack = Array(Signal() for _ in range(num_pe))
			barrier_done = Signal()

			self.comb += barrier_done.eq(optree("&", barrier_ack)), have_barrier.eq(self.scatter[source].network_interface.msg.barrier & self.scatter[source].network_interface.valid)

			self.sync += If(have_barrier & ~barrier_done,
							[barrier_ack[i].eq(barrier_ack[i] | array_writable[i]) for i in range(num_pe)]
						 ).Else(
						 	[barrier_ack[i].eq(0) for i in range(num_pe)]
						 )

			sink = Signal(addresslayout.peidsize)

			self.comb+= If(have_barrier,
							[array_barrier[i].eq(1) for i in range(num_pe)],
							[array_we[i].eq(~barrier_ack[i]) for i in range(num_pe)],
							self.scatter[source].network_interface.ack.eq(barrier_done)
						).Else(
							sink.eq(self.scatter[source].network_interface.dest_pe),\
							array_dest_id[sink].eq(self.scatter[source].network_interface.msg.dest_id),\
							array_parent[sink].eq(self.scatter[source].network_interface.msg.parent),\
							array_we[sink].eq(self.scatter[source].network_interface.valid),\
							self.scatter[source].network_interface.ack.eq(array_writable[sink])
						)

		# state of calculation
		self.global_inactive = Signal()
		self.comb += self.global_inactive.eq(optree("&", [pe.inactive for pe in self.apply]))

		# module for controlling execution
		self.submodules.initgraph = BFSInitGraph(addresslayout=addresslayout, wr_ports_idx=[self.scatter[i].wr_port_idx for i in range(num_pe)], wr_ports_val=[self.scatter[i].get_neighbors.wr_port_val for i in range(num_pe)], rd_ports_node=[appli.extern_rd_port for appli in self.apply], rx=rx, tx=tx, start_message=[self.arbiter[i].start_message for i in range(num_pe)], end=self.global_inactive, init_node=init_node)

class WrappedBFS(riffa.GenericRiffa):
	def __init__(self, addresslayout, combined_interface_rx, combined_interface_tx, c_pci_data_width=32, init_node=6):
		riffa.GenericRiffa.__init__(self, combined_interface_rx=combined_interface_rx, combined_interface_tx=combined_interface_tx, c_pci_data_width=c_pci_data_width)
		rx, tx = self.get_channel(0)
		self.submodules.bfs = BFS(addresslayout, rx, tx)
		self.ext_clk = Signal()
		self.ext_rst = Signal()
		rst1 = Signal()
		self.specials += [
			Instance("FDPE", p_INIT=1, i_D=0, i_PRE=self.ext_rst,
				i_CE=1, i_C=self.cd_sys.clk, o_Q=rst1),
			Instance("FDPE", p_INIT=1, i_D=rst1, i_PRE=self.ext_rst,
				i_CE=1, i_C=self.cd_sys.clk, o_Q=self.cd_sys.rst)
		]
		self.comb += self.cd_sys.clk.eq(self.ext_clk)

def main():
	c_pci_data_width = 128
	num_chnls = 2
	combined_interface_tx = riffa.Interface(data_width=c_pci_data_width, num_chnls=num_chnls)
	combined_interface_rx = riffa.Interface(data_width=c_pci_data_width, num_chnls=num_chnls)

	nodeidsize = 16
	num_nodes_per_pe = 2**8
	edgeidsize = 16
	max_edges_per_pe = 2**12
	peidsize = 8
	num_pe = 8

	# nodeidsize = 8
	# num_nodes_per_pe = 2**2
	# edgeidsize = 8
	# max_edges_per_pe = 2**4
	# peidsize = 1
	# num_pe = 2

	pcie_width = 128

	addresslayout = BFSAddressLayout(nodeidsize, edgeidsize, peidsize, num_pe, num_nodes_per_pe, max_edges_per_pe)

	m = WrappedBFS(addresslayout, combined_interface_rx, combined_interface_tx, c_pci_data_width=pcie_width)

	# add a loopback to test responsiveness
	test_rx, test_tx = m.get_channel(num_chnls - 1)
	m.comb += test_rx.connect(test_tx)

	m.ext_clk.name_override="clk"
	m.ext_rst.name_override="rst"
	for name in "ack", "last", "len", "off", "data", "data_valid", "data_ren":
		getattr(combined_interface_rx, name).name_override="chnl_rx_{}".format(name)
		getattr(combined_interface_tx, name).name_override="chnl_tx_{}".format(name)
	combined_interface_rx.start.name_override="chnl_rx"
	combined_interface_tx.start.name_override="chnl_tx"
	m.rx_clk.name_override="chnl_rx_clk"
	m.tx_clk.name_override="chnl_tx_clk"
	print(verilog.convert(m, name="top", ios={getattr(combined_interface_rx, name) for name in ["start", "ack", "last", "len", "off", "data", "data_valid", "data_ren"]} | {getattr(combined_interface_tx, name) for name in ["start", "ack", "last", "len", "off", "data", "data_valid", "data_ren"]} | {m.rx_clk, m.tx_clk, m.ext_clk, m.ext_rst} ))


if __name__ == '__main__':
	main()