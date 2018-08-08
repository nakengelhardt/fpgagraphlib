#include "applykernel.h"
#include "init.h"
#include <iostream>

static int start_round = 0;
static int current_round_edges = 0;

void initVertexData(VertexEntry* init_data, vertexid_t vertex, Graph* graph){
    init_data->data.num_triangles = 0;
    if ( vertex < graph->nv && vertex >= 0 ) {
        init_data->data.send_in_level = start_round;
        init_data->data.active = 1;
        int num_neighbors = graph->num_neighbors(vertex);
        current_round_edges += num_neighbors;
        if(current_round_edges > (1<<12)) {
            start_round++;
            current_round_edges = 0;
        }
    } else {
        init_data->data.send_in_level = 0;
        init_data->data.active = 0;
    }
}

void sendInitMessages(Graph* graph, PE** pe, int* sent){

}

void printFinalResult() {
    std::cout << "Total number of triangles in the graph: " << ApplyKernel::total_triangles << std::endl;
}
