/* Machine-generated using Migen */
module vsssp_scatter(
	input [7:0] update_in_dist,
	input [31:0] num_neighbors_in,
	input [31:0] neighbor_in,
	input [7:0] edgedata_in_dist,
	input [31:0] sender_in,
	input [1:0] round_in,
	input barrier_in,
	input valid_in,
	output ready,
	output reg [7:0] message_out_dist,
	output reg [31:0] neighbor_out,
	output reg [31:0] sender_out,
	output reg [1:0] round_out,
	output reg valid_out,
	input message_ack,
	output reg barrier_out,
	input sys_clk//,
	//input sys_rst
);



assign ready = message_ack;

always @(posedge sys_clk) begin
	if (message_ack) begin
		message_out_dist <= (update_in_dist + edgedata_in_dist);
		neighbor_out <= neighbor_in;
		sender_out <= sender_in;
		round_out <= round_in;
		valid_out <= valid_in;
		barrier_out <= barrier_in;
	end
end

endmodule
