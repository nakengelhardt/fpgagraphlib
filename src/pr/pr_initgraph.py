from migen.fhdl.std import *
from migen.genlib.fsm import FSM, NextState, NextValue
from migen.genlib.misc import optree

from pr_address import PRAddressLayout

class PRInitGraph(Module):
	def __init__(self, addresslayout, wr_ports_idx, wr_ports_val, rd_ports_node, rx, tx, cmd_tx, start_message, end, init_node=1):
		nodeidsize = addresslayout.nodeidsize
		edgeidsize = addresslayout.edgeidsize
		peidsize = addresslayout.peidsize
		num_nodes_per_pe = addresslayout.num_nodes_per_pe
		num_pe = addresslayout.num_pe
		max_edges_per_pe = addresslayout.max_edges_per_pe

		init_node_pe = init_node//num_nodes_per_pe

		pcie_width = rx.data_width
		num_idx_per_line = pcie_width//(2*edgeidsize)
		num_val_per_line = pcie_width//nodeidsize

		curr_address = Signal(nodeidsize)
		end_address = Signal(nodeidsize)

		we_idx_array = Array(wr_port_idx.we for wr_port_idx in wr_ports_idx)
		we_val_array = Array(wr_port_val.we for wr_port_val in wr_ports_val)

		self.cycles_calc = Signal(64)

		fsm = FSM()
		self.submodules += fsm
		fsm.act("WAIT_IDX",
			rx.ack.eq(1),
			NextValue(curr_address, 0),
			NextValue(end_address, num_pe*num_nodes_per_pe - 1),
			If(rx.start,
				NextState("FILL_IDX")
			)
		)
		fsm.act("FILL_IDX",
			[If(curr_address[0:log2_int(num_idx_per_line)]==i, wr_port_idx.dat_w.eq(rx.data[i*flen(wr_port_idx.dat_w):(i+1)*flen(wr_port_idx.dat_w)])) for wr_port_idx in wr_ports_idx for i in range(num_idx_per_line)],
			[wr_port_idx.adr.eq(addresslayout.local_adr(curr_address)) for wr_port_idx in wr_ports_idx],
			rx.data_ren.eq(curr_address[0:log2_int(num_idx_per_line)]==num_idx_per_line-1),
			If(rx.data_valid,
				we_idx_array[addresslayout.pe_adr(curr_address)].eq(1),
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
			NextValue(end_address, num_pe*max_edges_per_pe - 1),
			If(rx.start,
				NextState("FILL_VAL")
			)
		)
		fsm.act("FILL_VAL",
			[If(curr_address[0:log2_int(num_val_per_line)]==i, wr_port_val.dat_w.eq(rx.data[i*flen(wr_ports_val[0].dat_w):(i+1)*flen(wr_ports_val[0].dat_w)])) for wr_port_val in wr_ports_val for i in range(num_val_per_line)],
			[wr_port_val.adr.eq(curr_address[0:log2_int(max_edges_per_pe)]) for wr_port_val in wr_ports_val],
			rx.data_ren.eq(curr_address[0:log2_int(num_val_per_line)]==num_val_per_line-1),
			If(rx.data_valid,
				we_val_array[curr_address[log2_int(max_edges_per_pe):]].eq(1),
				If(curr_address < end_address,
					NextValue(curr_address, curr_address+1)
				).Else(
					NextState("TX_CMD_START")
				)
			)
		)
		fsm.act("TX_CMD_START",
			cmd_tx.start.eq(1),
			cmd_tx.len.eq(num_nodes_per_pe*4),
			cmd_tx.last.eq(1),
			cmd_tx.off.eq(0),
			NextValue(curr_address, 0),
			NextValue(end_address, num_nodes_per_pe-1),
			[wr_port_idx.adr.eq(0) for wr_port_idx in wr_ports_idx],
			[If(curr_address[0:log2_int(num_val_per_line)]==i, cmd_tx.data.eq(wr_ports_val[i].dat_r)) for i in range(num_pe)],
			If(cmd_tx.ack,
				NextState("TX_CMD")
			)
		)
		fsm.act("TX_CMD",
			cmd_tx.start.eq(1),
			cmd_tx.len.eq(num_nodes_per_pe*4),
			cmd_tx.last.eq(1),
			cmd_tx.off.eq(0),
			[wr_port_idx.adr.eq(addresslayout.local_adr(curr_address)) for wr_port_idx in wr_ports_idx],
			[If(curr_address[0:log2_int(num_val_per_line)]==i, cmd_tx.data.eq(wr_ports_val[i].dat_r)) for i in range(num_pe)],
			cmd_tx.data_valid.eq(1),
			If(cmd_tx.data_ren & cmd_tx.data_valid,
				NextValue(curr_address, curr_address+1)
			),
			If(curr_address >= end_address,
				NextState("INIT_CALC")
			)
		)
		fsm.act("INIT_CALC",
			# send a message to each node
			start_message[init_node_pe].msg.dest_id.eq(init_node),
			start_message[init_node_pe].msg.payload.eq(init_node),
			start_message[init_node_pe].msg.barrier.eq(0),
			start_message[init_node_pe].valid.eq(1),
			If(start_message[init_node_pe].ack,
				NextState("ADD_BARRIER")
			)
		)

		barrier_ack = Array(Signal() for _ in range(num_pe))
		barrier_done = Signal()

		self.comb += barrier_done.eq(optree("&", barrier_ack))

		fsm.act("ADD_BARRIER",
			[start_message[i].msg.dest_id.eq(0) for i in range(num_pe)],
			[start_message[i].msg.payload.eq(0) for i in range(num_pe)],
			[start_message[i].msg.barrier.eq(1) for i in range(num_pe)],
			[start_message[i].valid.eq(~barrier_ack[i]) for i in range(num_pe)],
			[NextValue(barrier_ack[i], barrier_ack[i] | start_message[init_node_pe].ack) for i in range(num_pe)],
			If(barrier_done,
				[NextValue(barrier_ack[i], 0) for i in range(num_pe)],
				NextValue(self.cycles_calc, 0),
				NextState("WAIT_END")
			)
		)
		fsm.act("WAIT_END",
			NextValue(self.cycles_calc, self.cycles_calc+1),
			If(end,
				NextValue(curr_address, 0),
				NextState("TX_RESULT_START")
			)
		)

		rd_ports_data = Array(rd_port.dat_r for rd_port in rd_ports_node)
		rd_ports_re = Array(rd_port.re for rd_port in rd_ports_node)

		# which port to take read result from
		# is used one cycle later than curr_address
		pe_adr = Signal(peidsize)
		self.sync += pe_adr.eq(addresslayout.pe_adr(curr_address))

		self.comb += [rd_port.adr.eq(addresslayout.local_adr(curr_address)) for rd_port in rd_ports_node], \
					 tx.data.eq(rd_ports_data[pe_adr])
		
		fsm.act("TX_RESULT_START",
			[rd_port.enable.eq(1) for rd_port in rd_ports_node],
			[rd_port.re.eq(1) for rd_port in rd_ports_node],
			tx.start.eq(1),
			tx.len.eq(num_pe*num_nodes_per_pe*4),
			tx.last.eq(1),
			tx.off.eq(0),
			If(tx.ack,
				[rd_port.re.eq(0) for rd_port in rd_ports_node],
				NextValue(curr_address, curr_address+1),
				NextValue(end_address, num_pe*num_nodes_per_pe),
				NextValue(tx.data_valid, 1),
				NextState("TX_RESULT_TRANSMIT")
			)
		)
		fsm.act("TX_RESULT_TRANSMIT",
			[rd_port.enable.eq(1) for rd_port in rd_ports_node],
			tx.start.eq(1),
			tx.len.eq(num_pe*num_nodes_per_pe*4),
			tx.last.eq(1),
			tx.off.eq(0),
			If(tx.data_ren & tx.data_valid,
				[rd_port.re.eq(1) for rd_port in rd_ports_node],
				NextValue(tx.data_valid, 1),
				NextValue(curr_address, curr_address+1)
			),
			If(curr_address >= end_address,
				NextValue(tx.data_valid, 0),
				NextState("CLEAR_MEM_START")
			)
		)
		fsm.act("CLEAR_MEM_START",
			NextValue(curr_address, 0),
			NextState("CLEAR_MEM")
		)
		fsm.act("CLEAR_MEM",
			start_message[addresslayout.pe_adr(curr_address)].msg.dest_id.eq(addresslayout.local_adr(curr_address)),
			start_message[addresslayout.pe_adr(curr_address)].msg.payload.eq(0),
			start_message[addresslayout.pe_adr(curr_address)].msg.barrier.eq(0),
			start_message[addresslayout.pe_adr(curr_address)].valid.eq(1),
			If(start_message[addresslayout.pe_adr(curr_address)].ack,
				NextValue(curr_address, curr_address + 1),
				If(curr_address >= (end_address-1),
					NextState("WAIT_IDX")
				)
			)
		)