#include "applykernel.h"
#include "init.h"
#include <iostream>


void initVertexData(VertexEntry* init_data, vertexid_t vertex, Graph* graph){
    init_data->data.num_triangles = 0;
    init_data->data.send_in_level = vertex % 6;
    init_data->active = 1;
}

void sendInitMessages(Graph* graph, PE** pe, int* sent){

}

void printFinalResult() {
    std::cout << "Total number of triangles in the graph: " << ApplyKernel::total_triangles << std::endl;
}
