/* Machine-generated using Migen */
module vbfs_gather(
	input [31:0] level_in,
	input [31:0] nodeid_in,
	input [31:0] sender_in,
	input message_in_dummy,
	input [31:0] state_in_parent,
	input state_in_active,
	input valid_in,
	output ready,
	output [31:0] nodeid_out,
	output reg [31:0] state_out_parent,
	output reg state_out_active,
	output state_valid,
	input state_ack,
	input sys_clk//,
	//input sys_rst
);

wire visited;


// Adding a dummy event (using a dummy signal 'dummy_s') to get the simulator
// to run the combinatorial process once at the beginning.
// synthesis translate_off
reg dummy_s;
initial dummy_s <= 1'd0;
// synthesis translate_on

assign visited = (state_in_parent != 1'd0);

// synthesis translate_off
reg dummy_d;
// synthesis translate_on
always @(*) begin
	state_out_parent <= 32'd0;
	state_out_active <= 1'd0;
	if (visited) begin
		state_out_parent <= state_in_parent;
		state_out_active <= state_in_active;
	end else begin
		state_out_parent <= sender_in;
		state_out_active <= 1'd1;
	end
// synthesis translate_off
	dummy_d <= dummy_s;
// synthesis translate_on
end
assign state_valid = valid_in;
assign nodeid_out = nodeid_in;
assign ready = state_ack;

endmodule
