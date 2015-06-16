from migen.fhdl.std import *
from migen.genlib.fifo import SyncFIFO

from bfs_interfaces import BFSApplyInterface, BFSScatterInterface, BFSMessage
from bfs_arbiter import BFSArbiter
from bfs_apply import BFSApply
from bfs_scatter import BFSScatter
from bfs_address import BFSAddressLayout
from bfs_initgraph import BFSInitGraph

class BFS(Module):
	def __init__(self, addresslayout, rx, tx, adj_mat=None):
		self.addresslayout = addresslayout
		nodeidsize = addresslayout.nodeidsize
		num_nodes_per_pe = addresslayout.num_nodes_per_pe
		num_pe = addresslayout.num_pe
		max_edges_per_pe = addresslayout.max_edges_per_pe

		fifos = [[SyncFIFO(width_or_layout=BFSMessage(nodeidsize).layout, depth=32) for _ in range(num_pe)] for _ in range(num_pe)]
		self.submodules.fifos = fifos
		self.submodules.arbiter = [BFSArbiter(addresslayout, fifos[i]) for i in range(num_pe)]
		self.submodules.apply = [BFSApply(addresslayout) for _ in range(num_pe)]
		self.submodules.scatter = [BFSScatter(addresslayout) for i in range(num_pe)]

		# connect within PEs
		self.comb += [self.arbiter[i].apply_interface.connect(self.apply[i].apply_interface) for i in range(num_pe)],\
					 [self.apply[i].scatter_interface.connect(self.scatter[i].scatter_interface) for i in range(num_pe)]

		# connect fifos across PEs
		for i in range(num_pe):
			array_dest_id = Array(fifo.din.dest_id for fifo in [fifos[j][i] for j in range(num_pe)])
			array_parent = Array(fifo.din.parent for fifo in [fifos[j][i] for j in range(num_pe)])
			array_we = Array(fifo.we for fifo in [fifos[j][i] for j in range(num_pe)])
			array_writable = Array(fifo.writable for fifo in [fifos[j][i] for j in range(num_pe)])

			dest_pe = Signal(log2_int(num_pe))
			self.comb+= dest_pe.eq(self.scatter[i].network_interface.dest_pe),\
						array_dest_id[dest_pe].eq(self.scatter[i].network_interface.msg.dest_id),\
						array_parent[dest_pe].eq(self.scatter[i].network_interface.msg.parent),\
						array_we[dest_pe].eq(self.scatter[i].network_interface.valid),\
						self.scatter[i].network_interface.ack.eq(array_writable[dest_pe])

		# module for controlling execution
		init_node = 6
		init_node_pe = init_node//num_nodes_per_pe
		self.submodules.initgraph = BFSInitGraph(addresslayout=addresslayout, wr_ports_idx=[self.scatter[i].wr_port_idx for i in range(num_pe)], wr_ports_val=[self.scatter[i].get_neighbors.wr_port_val for i in range(num_pe)], rx=rx, tx=tx, start_message=self.arbiter[init_node_pe].start_message, init_node=init_node)
