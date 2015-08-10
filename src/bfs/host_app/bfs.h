#ifndef BFS_H
#define BFS_H

/*  nodeidsize = 16
	num_nodes_per_pe = 2**8
	edgeidsize = 16
	max_edges_per_pe = 2**10
	peidsize = 8
	num_pe = 16 */

#define NODE_ADR_BITS 8
#define PE_ADR_BITS 8
#define NUM_PE 16
#define NUM_NODES (1 << NODE_ADR_BITS)
#define NUM_EDGES (1 << 12)

#define NODE_ADR(node) ((node) & (NUM_NODES - 1))
#define PE_ADR(node) (((node) & ~(NUM_NODES - 1)) >> NODE_ADR_BITS)

typedef uint16_t nodeID_t;
typedef uint16_t edgeID_t;
typedef struct {edgeID_t start; edgeID_t num;} edgeIdx_t;
typedef struct {uint32_t parent; uint32_t pad0; uint32_t pad1; uint32_t pad2;} nodeRet_t;


extern nodeRet_t node_out_buffers[NUM_PE][NUM_NODES];
extern const int node_out_buffers_size;

extern edgeIdx_t edge_idx_in_buffers[NUM_PE][NUM_NODES];
extern const int edge_idx_in_buffers_size;
extern nodeID_t edge_val_in_buffers[NUM_PE][NUM_EDGES];
extern const int edge_val_in_buffers_size;

void parse_graph(FILE* fp, int directed);
void print_graph();

#endif