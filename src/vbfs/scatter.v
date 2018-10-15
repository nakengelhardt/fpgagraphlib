/* Machine-generated using Migen */
module vbfs_scatter(
	input update_in_dummy,
	input [31:0] num_neighbors_in,
	input [31:0] neighbor_in,
	input [31:0] sender_in,
	input [1:0] round_in,
	input barrier_in,
	input valid_in,
	output ready,
	input message_out_dummy,
	output [31:0] neighbor_out,
	output [31:0] sender_out,
	output [1:0] round_out,
	output valid_out,
	input message_ack,
	output barrier_out,
	input sys_clk//,
	//input sys_rst
);



// Adding a dummy event (using a dummy signal 'dummy_s') to get the simulator
// to run the combinatorial process once at the beginning.
// synthesis translate_off
reg dummy_s;
initial dummy_s <= 1'd0;
// synthesis translate_on

assign neighbor_out = neighbor_in;
assign sender_out = sender_in;
assign round_out = round_in;
assign valid_out = valid_in;
assign barrier_out = barrier_in;
assign ready = message_ack;

endmodule
