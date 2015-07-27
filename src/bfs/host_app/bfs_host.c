#include <stdlib.h>
#include <stdio.h>
#include <stdint.h>
#include "riffa.h"

/*  nodeidsize = 8
	num_nodes_per_pe = 2**2
	edgeidsize = 8
	max_edges_per_pe = 2**4
	peidsize = 3
	num_pe = 8 */

#define NUM_PE 8
#define NUM_NODES 4
#define NUM_EDGES 16

char* testmessage = "This is the Happiness and Peace of Mind Committee";

typedef uint8_t NODEID;
typedef uint8_t EDGEID;
typedef struct {EDGEID start; EDGEID num;} EDGE_IDX;
typedef struct {uint32_t parent; uint32_t pad0; uint32_t pad1; uint32_t pad2;} NODERETURNSTRUCT;

NODERETURNSTRUCT node_out_buffers[NUM_PE][NUM_NODES];
int node_out_buffers_size = NUM_PE*NUM_NODES*sizeof(NODERETURNSTRUCT);

EDGE_IDX edge_idx_in_buffers[NUM_PE][NUM_NODES];
int edge_idx_in_buffers_size = NUM_PE*NUM_NODES*sizeof(EDGE_IDX);
NODEID edge_val_in_buffers[NUM_PE][NUM_EDGES];
int edge_val_in_buffers_size = NUM_PE*NUM_EDGES*sizeof(NODEID);



int main (int argc, char *argv[]) {

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
	sent = fpga_send(fpga, chnl, edge_val_in_buffers, edge_idx_in_buffers_size/4, 0, 1, 25000);
	printf("Sent edge value array: %d bytes\n", sent*4);

	recvd = fpga_recv(fpga, chnl, node_out_buffers, node_out_buffers_size/4, 25000);
	printf("Received node data: %d bytes\n", recvd*4);

	int pe, n;
	printf("Minimal spanning tree:\n");
	for(pe=0; pe<NUM_PE; pe++){
		for(n=0; n<NUM_NODES; n++){
			printf("%d <- %d\n", pe*NUM_NODES+n, node_out_buffers[pe][m].parent);
		}
	}
	fpga_close(fpga);
	return 0;
}