#include <stdlib.h>
#include <stdio.h>
#include <stdint.h>
#define JUDYERROR_SAMPLE 1
#include "Judy.h"
#include "bfs.h"

#define MAXLINELEN 256           // define maximum string length

struct node_t{
	nodeID_t id;
	struct node_t* next;
};

typedef struct node_t node_t;

int last_node_id;
node_t* nodes[NUM_PE*NUM_NODES];

Pvoid_t PJSLArray = (Pvoid_t) NULL;  // initialize JudySL array

node_t* get_node(const uint8_t* key){
	Word_t* PValue;
	JSLG( PValue,  PJSLArray, key);
	if(!PValue){
		++last_node_id;
		node_t* new_node = (node_t*) malloc(sizeof(node_t));
		new_node->id = last_node_id;
		new_node->next = NULL;
		if(last_node_id >= NUM_PE*NUM_NODES){
			fprintf(stderr, "Too many nodes for chosen PE number and size!\n");
			exit(-1);
		}
		//printf("Creating node %s: internally %d\n", key, last_node_id);
		nodes[last_node_id] = new_node;
		JSLI( PValue,  PJSLArray, key);
		*PValue = (Word_t) new_node;
	}
	return (node_t*) *PValue;
}

void insert_edge_directed(node_t* source_n, const node_t* sink_n){
	node_t* curr_n = source_n;
	while(curr_n->next){
		if(curr_n->id == sink_n->id){ //edge already exists
			return;
		}
		curr_n = curr_n->next;
	}
	node_t* edge = (node_t*) malloc(sizeof(node_t));
	edge->id = sink_n->id;
	edge->next = NULL;
	curr_n->next = edge;
	return;
}

void insert_edge(const uint8_t* source, const uint8_t* sink, int directed){
	//printf("Insert edge: %s -> %s\n", source, sink);
	node_t *source_n, *sink_n;
	source_n = get_node(source);
	sink_n = get_node(sink);
	insert_edge_directed(source_n, sink_n);
	if(!directed){
		insert_edge_directed(sink_n, source_n);
	}
	return;
}

void free_node_and_neighbors(node_t* node){
	node_t* curr = node;
	node_t* prev;
	while(curr){
		prev = curr;
		curr = curr->next;
		free(prev);
	}
	return;
}



/* parses graph into global CSR arrays edgeIdx_t edge_idx_in_buffers[][], nodeID_t edge_val_in_buffers[][] (defined in bfs.h) */
void parse_graph(FILE* fp, int directed){
	uint8_t line[MAXLINELEN*4], source[MAXLINELEN], sink[MAXLINELEN];
	last_node_id = 0;

	while(fgets((char*)line, MAXLINELEN*4, fp)){
		sscanf((char*)line, "%s %s *", source, sink);
		insert_edge(source, sink, directed);
	}

	edge_idx_in_buffers[0][0] = (edgeIdx_t) {0, 0};
	int n;
	for(n=1; n<=last_node_id; n++){
		uint8_t start_idx, num;
		if(NODE_ADR(n) > 0){
			edgeIdx_t prev = edge_idx_in_buffers[PE_ADR(n)][NODE_ADR(n-1)];
			start_idx = prev.start + prev.num;
		} else {
			start_idx = 0;
		}
		num = 0;
		node_t* curr_n = nodes[n];
		if(curr_n->id != n){
			fprintf(stderr, "Sorting error: node with id %d in field %d.\n", curr_n->id, n);
			exit(-1);
		}
		while((curr_n = curr_n->next)){
			if(start_idx + num >= NUM_EDGES){
				fprintf(stderr, "Error: Ran out of edge storage space on PE %d.\n", PE_ADR(n));
				exit(-1);
			}
			edge_val_in_buffers[PE_ADR(n)][start_idx + num] = curr_n->id;
			num++;
		}
		edge_idx_in_buffers[PE_ADR(n)][NODE_ADR(n)].start = start_idx;
		edge_idx_in_buffers[PE_ADR(n)][NODE_ADR(n)].num = num;
		free_node_and_neighbors(nodes[n]);
	}

	return;
}

void print_graph(){
	for(int n=1; n<=last_node_id; n++){
		printf("Node %d:", n);
		for (int i = 0; i < edge_idx_in_buffers[PE_ADR(n)][NODE_ADR(n)].num; ++i)
		{
			printf(" %d", edge_val_in_buffers[PE_ADR(n)][edge_idx_in_buffers[PE_ADR(n)][NODE_ADR(n)].start + i]);
		}
		printf("\n");
	}
}