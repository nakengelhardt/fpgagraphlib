/* Machine-generated using Migen */
module vbfs_apply(
	input [31:0] nodeid_in,
	input [31:0] state_in_parent,
	input state_in_active,
	input state_in_valid,
	input valid_in,
	input [1:0] round_in,
	input barrier_in,
	output ready,
	output [31:0] nodeid_out,
	output [31:0] state_out_parent,
	output state_out_active,
	output state_valid,
	output state_barrier,
	input state_ack,
	output update_out_dummy,
	output [31:0] update_sender,
	output update_valid,
	output [1:0] update_round,
	output barrier_out,
	input update_ack,
	output kernel_error,
	input sys_clk//,
	//input sys_rst
);



// Adding a dummy event (using a dummy signal 'dummy_s') to get the simulator
// to run the combinatorial process once at the beginning.
// synthesis translate_off
reg dummy_s;
initial dummy_s <= 1'd0;
// synthesis translate_on

assign nodeid_out = nodeid_in;
assign state_out_parent = state_in_parent;
assign state_out_active = 1'd0;
assign state_valid = ((valid_in & state_in_valid) & update_ack);
assign state_barrier = (barrier_in & valid_in);
assign update_out_dummy = 1'd0;
assign update_sender = nodeid_in;
assign update_round = round_in;
assign update_valid = ((valid_in & ((state_in_valid & state_in_active) | barrier_in)) & state_ack);
assign barrier_out = barrier_in;
assign ready = (update_ack & state_ack);
assign kernel_error = 1'd0;

endmodule
