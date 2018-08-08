#include "init.h"


void initVertexData(VertexEntry* init_data, vertexid_t vertex, Graph* graph){
    if ( vertex < graph->nv && vertex >= 0 ) {
        init_data->data.active = 1;
        init_data->data.color = vertex;
    } else {
        init_data->data.active = 0;
        init_data->data.color = 0;
    }
}

void printFinalResult() {
}
