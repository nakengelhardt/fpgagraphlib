#include "init.h"


void initVertexData(VertexEntry* init_data, vertexid_t vertex, Graph* graph){
    init_data->data.dist = 255;
    init_data->data.parent = 0;
    if ( vertex == 0 ) {
        init_data->data.active = true;
    } else {
        init_data->data.active = false;
    }
}

void printFinalResult() {
}
