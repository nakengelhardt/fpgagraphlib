#include "applykernel.h"
#include "init.h"
#include <iostream>

int start_round = 0;
int current_round_edges = 0;

void initVertexData(VertexEntry* init_data, vertexid_t vertex, Graph* graph){
    init_data->data.num_triangles = 0;
    int num_neighbors = graph->num_neighbors(vertex);
    if(num_neighbors > (1024 - current_round_edges)) {
        start_round++;
        current_round_edges = 0;
    }
    init_data->data.send_in_level = start_round;
    current_round_edges += num_neighbors;
    init_data->active = 1;
}

void sendInitMessages(Graph* graph, PE** pe, int* sent){

}

void printFinalResult() {
    std::cout << "Total number of triangles in the graph: " << ApplyKernel::total_triangles << std::endl;
}
