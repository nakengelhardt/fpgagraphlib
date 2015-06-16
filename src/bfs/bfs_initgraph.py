from migen.fhdl.std import *
from migen.genlib.fsm import FSM, NextState, NextValue

from bfs_address import BFSAddressLayout
from bfs_interfaces import BFSApplyInterface

class BFSInitGraph(Module):
	def __init__(self, addresslayout, wr_ports_idx, wr_ports_val, rx, tx, start_message, init_node=1):
		nodeidsize = addresslayout.nodeidsize
		edgeidsize = addresslayout.edgeidsize
		peidsize = addresslayout.peidsize
		num_nodes_per_pe = addresslayout.num_nodes_per_pe
		num_pe = addresslayout.num_pe
		max_edges_per_pe = addresslayout.max_edges_per_pe


		num_idx_per_line = addresslayout.num_idx_per_line
		num_val_per_line = addresslayout.num_val_per_line
		pcie_width = addresslayout.pcie_width

		curr_address = Signal(nodeidsize)
		end_address = Signal(nodeidsize)

		we_idx_array = Array(wr_port_idx.we for wr_port_idx in wr_ports_idx)
		we_val_array = Array(wr_port_val.we for wr_port_val in wr_ports_val)

		fsm = FSM()
		self.submodules += fsm
		fsm.act("WAIT_IDX",
			rx.ack.eq(1),
			NextValue(curr_address, 0),
			If(rx.start,
				NextValue(end_address, ((rx.len << 5) >> log2_int(2*edgeidsize)) -1),
				NextState("FILL_IDX")
			)
		)
		fsm.act("FILL_IDX",
			[If(curr_address[0:log2_int(num_idx_per_line)]==i, wr_port_idx.dat_w.eq(rx.data[i*flen(wr_port_idx.dat_w):(i+1)*flen(wr_port_idx.dat_w)])) for wr_port_idx in wr_ports_idx for i in range(num_idx_per_line)],
			[wr_port_idx.adr.eq(addresslayout.local_adr(curr_address)) for wr_port_idx in wr_ports_idx],
			If(rx.data_valid,
				we_idx_array[addresslayout.pe_adr(curr_address)].eq(1),
				rx.data_ren.eq(curr_address[0:log2_int(num_idx_per_line)]==num_idx_per_line-1),
				If(curr_address < end_address,
					NextValue(curr_address, curr_address+1)
				).Else(
					NextState("WAIT_VAL")
				)
			)
		)
		fsm.act("WAIT_VAL",
			rx.ack.eq(1),
			NextValue(curr_address, 0),
			If(rx.start,
				NextValue(end_address, ((rx.len << 5) >> log2_int(nodeidsize)) - 1),
				NextState("FILL_VAL")
			)
		)
		fsm.act("FILL_VAL",
			[If(curr_address[0:log2_int(num_val_per_line)]==i, wr_port_val.dat_w.eq(rx.data[i*flen(wr_ports_val[0].dat_w):(i+1)*flen(wr_ports_val[0].dat_w)])) for wr_port_val in wr_ports_val for i in range(num_val_per_line)],
			[wr_port_val.adr.eq(curr_address[0:log2_int(max_edges_per_pe)]) for wr_port_val in wr_ports_val],
			If(rx.data_valid,
				we_val_array[curr_address[log2_int(max_edges_per_pe):]].eq(1),
				rx.data_ren.eq(curr_address[0:log2_int(num_val_per_line)]==num_val_per_line-1),
				If(curr_address < end_address,
					NextValue(curr_address, curr_address+1)
				).Else(
					NextState("INIT_CALC")
				)
			)
		)
		fsm.act("INIT_CALC",
			start_message.msg.dest_id.eq(init_node),
			start_message.msg.parent.eq(init_node),
			start_message.valid.eq(1),
			If(start_message.ack,
				NextState("WAIT_IDX")
			)
		)