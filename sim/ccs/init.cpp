#include "init.h"


void initVertexData(VertexEntry* init_data, vertexid_t vertex, Graph* graph){
    init_data->data.color = vertex;
    init_data->active = 1;
}

void sendInitMessages(Graph* graph, PE** pe, int* sent){

}

void printFinalResult() {
}
