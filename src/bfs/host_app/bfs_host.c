#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include "riffa.h"
#include "bfs.h"

char testmessage[] = "This is the Happiness and Peace of Mind Committee. ";

#define RIFFABUFSZ(x) (((x) + 3)/4)

nodeRet_t node_out_buffers[NUM_PE][NUM_NODES];
const int node_out_buffers_size = NUM_PE*NUM_NODES*sizeof(nodeRet_t);

edgeIdx_t edge_idx_in_buffers[NUM_PE][NUM_NODES];
const int edge_idx_in_buffers_size = NUM_PE*NUM_NODES*sizeof(edgeIdx_t);
nodeID_t edge_val_in_buffers[NUM_PE][NUM_EDGES];
const int edge_val_in_buffers_size = NUM_PE*NUM_EDGES*sizeof(nodeID_t);

int main (int argc, char *argv[]) {

	if(argc < 2){
		fprintf(stderr, "Usage: %s graphfile\n", argv[0]);
		exit(-1);
	}

	FILE* fp = fopen(argv[1], "r");

	parse_graph(fp, 0);
	// print_graph();

	fpga_t * fpga;
	int id = 0;

	fpga = fpga_open(id);
	if (fpga == NULL) {
		fprintf(stderr, "Could not get FPGA %d\n", id);
		return -1;
	}

	// Reset
	fpga_reset(fpga);

	// Test communication on channel 2 (loopback)
	int chnl = 2;
	int sent, recvd;
	char* recvBuffer = (char*) malloc(sizeof(testmessage));
	if (recvBuffer == NULL) {
		printf("Could not malloc memory for recvBuffer\n");
		fpga_close(fpga);
		return -1;
	}
	// Send test data
	sent = fpga_send(fpga, chnl, testmessage, sizeof(testmessage)/4, 0, 1, 5000);
	recvd = fpga_recv(fpga, chnl, recvBuffer, sizeof(testmessage)/4, 5000);

	// if(!memcmp(testmessage, recvBuffer, sizeof(testmessage))){
	// 	printf("Echo test failed.\n");
		printf("Sent %d bytes:     \"%s\"\n", sent*4, testmessage);
		printf("Received %d bytes: \"%s\"\n", recvd*4, recvBuffer);
	// 	fpga_close(fpga);
	// 	return -1;
	// } else {
	// 	printf("Board responded: %s\n", recvBuffer);
	// }

	// Launch graph calc

	chnl = 0;
	int cmd_chnl = 1;

	sent = fpga_send(fpga, chnl, edge_idx_in_buffers, RIFFABUFSZ(edge_idx_in_buffers_size), 0, 1, 5000);
	printf("Sent edge index array: %d bytes\n", sent*4);
	sent = fpga_send(fpga, chnl, edge_val_in_buffers, RIFFABUFSZ(edge_val_in_buffers_size), 0, 1, 5000);
	printf("Sent edge value array: %d bytes\n", sent*4);

	int idx_echo_buffers_size = NUM_NODES*sizeof(nodeRet_t);
	nodeRet_t* idx_echo_buffers = (nodeRet_t*) malloc(idx_echo_buffers_size);

	recvd = fpga_recv(fpga, cmd_chnl, idx_echo_buffers, RIFFABUFSZ(idx_echo_buffers_size), 5000);
	printf("Received adj_idx back: %d bytes\n", recvd*4);

	for(int n=0; n<NUM_NODES; n++){
		printf("%d -> %d (%d %d %d)\n", n, idx_echo_buffers[n].parent, idx_echo_buffers[n].pad0, idx_echo_buffers[n].pad1, idx_echo_buffers[n].pad2);
	}

	

	recvd = fpga_recv(fpga, chnl, node_out_buffers, RIFFABUFSZ(node_out_buffers_size), 25000);
	printf("Received node data: %d bytes\n", recvd*4);

	// uint64_t ret[2];
	// recvd = fpga_recv(fpga, cmd_chnl, ret, 4, 5000);
	// printf("Received cmd: %lu %lu\n", ret[1], ret[0]);

	printf("Minimal spanning tree:\n");
	for(int pe=0; pe<NUM_PE; pe++){
		for(int n=0; n<NUM_NODES; n++){
			printf("%d -> %d (%d %d %d)\n", pe*NUM_NODES+n, node_out_buffers[pe][n].parent, node_out_buffers[pe][n].pad0, node_out_buffers[pe][n].pad1, node_out_buffers[pe][n].pad2);
		}
		printf("\n");
	}
	fpga_close(fpga);
	return 0;
}
