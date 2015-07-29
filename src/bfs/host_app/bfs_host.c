#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include "riffa.h"
#include "bfs.h"

char testmessage[] = "This is the Happiness and Peace of Mind Committee";

nodeRet_t node_out_buffers[NUM_PE][NUM_NODES];
const int node_out_buffers_size = NUM_PE*NUM_NODES*sizeof(nodeRet_t);

edgeIdx_t edge_idx_in_buffers[NUM_PE][NUM_NODES];
const int edge_idx_in_buffers_size = NUM_PE*NUM_NODES*sizeof(edgeIdx_t);
nodeID_t edge_val_in_buffers[NUM_PE][NUM_EDGES];
const int edge_val_in_buffers_size = NUM_PE*NUM_EDGES*sizeof(nodeID_t);

int main (int argc, char *argv[]) {

	if(argc < 2){
		fprintf(stderr, "Usage: %s graphfile\n", argv[0]);
	}

	FILE* fp = fopen(argv[1], "r");

	parse_graph(fp, 0);

	fpga_t * fpga;
	int id = 0;

	fpga = fpga_open(id);
	if (fpga == NULL) {
		fprintf(stderr, "Could not get FPGA %d\n", id);
		return -1;
	}

	// Reset
	fpga_reset(fpga);

	// Test communication on channel 1 (loopback)
	int chnl = 1;
	int sent, recvd;
	char* recvBuffer = (char*) malloc(sizeof(testmessage));
	if (recvBuffer == NULL) {
		printf("Could not malloc memory for recvBuffer\n");
		fpga_close(fpga);
		return -1;
	}
	// Send test data
	sent = fpga_send(fpga, chnl, testmessage, sizeof(testmessage)/4, 0, 1, 25000);
	recvd = fpga_recv(fpga, chnl, recvBuffer, sizeof(testmessage)/4, 25000);

	if(sent != sizeof(testmessage)/4 || sent != recvd || !memcmp(testmessage, recvBuffer, sizeof(testmessage))){
		printf("Echo test failed.\n");
		printf("Sent %d bytes:     \"%s\"\n", sent*4, testmessage);
		printf("Received %d bytes: \"%s\"\n", recvd*4, recvBuffer);
		fpga_close(fpga);
		return -1;
	}

	// Launch graph calc

	chnl = 0;

	sent = fpga_send(fpga, chnl, edge_idx_in_buffers, edge_idx_in_buffers_size/4, 0, 1, 25000);
	printf("Sent edge index array: %d bytes\n", sent*4);
	sent = fpga_send(fpga, chnl, edge_val_in_buffers, edge_val_in_buffers_size/4, 0, 1, 25000);
	printf("Sent edge value array: %d bytes\n", sent*4);

	recvd = fpga_recv(fpga, chnl, node_out_buffers, node_out_buffers_size/4, 25000);
	printf("Received node data: %d bytes\n", recvd*4);

	int pe, n;
	printf("Minimal spanning tree:\n");
	for(pe=0; pe<NUM_PE; pe++){
		for(n=0; n<NUM_NODES; n++){
			printf("%d <- %d\n", pe*NUM_NODES+n, node_out_buffers[pe][n].parent);
		}
	}
	fpga_close(fpga);
	return 0;
}