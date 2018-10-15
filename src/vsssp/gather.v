/* Machine-generated using Migen */
module vsssp_gather(
	input [31:0] level_in,
	input [31:0] nodeid_in,
	input [31:0] sender_in,
	input [7:0] message_in_dist,
	input [7:0] state_in_dist,
	input [31:0] state_in_parent,
	input state_in_active,
	input valid_in,
	output ready,
	output [31:0] nodeid_out,
	output [7:0] state_out_dist,
	output [31:0] state_out_parent,
	output state_out_active,
	output state_valid,
	input state_ack,
	input sys_clk//,
	//input sys_rst
);

wire new_path;
assign new_path = state_in_dist > message_in_dist;

assign nodeid_out = nodeid_in;
assign state_out_dist = new_path ? message_in_dist : state_in_dist;
assign state_out_parent = new_path ? sender_in : state_in_parent;
assign state_out_active = new_path ? 1'b1 : state_in_active;
assign state_valid = valid_in;
assign ready = state_ack;

assign state_valid = valid_in;
assign nodeid_out = nodeid_in;
assign ready = state_ack;

endmodule
