#include "init.h"
#include <iostream>


void initVertexData(VertexEntry* init_data, vertexid_t vertex, Graph* graph){
    if ( vertex < graph->nv && vertex >= 0 ) {
        init_data->data.nneighbors = graph->num_neighbors(vertex);
        init_data->data.nrecvd = graph->num_neighbors(vertex);
        init_data->data.sum = 0.15/graph->nv;
        init_data->data.active = true;
    } else {
        init_data->data.active = false;
    }
}

void printFinalResult() {
}
