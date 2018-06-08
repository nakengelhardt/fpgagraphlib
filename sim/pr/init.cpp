#include "init.h"
#include <iostream>


void initVertexData(VertexEntry* init_data, vertexid_t vertex, Graph* graph){
    init_data->data.nneighbors = graph->num_neighbors(vertex);
    init_data->data.nrecvd = graph->num_neighbors(vertex);
    init_data->data.sum = 0.15/graph->nv;
}

void sendInitMessages(Graph* graph, PE** pe, int* sent){
    Message* message;
    for(int i = 0; i < graph->nv; i++){
        message = new Message();
        message->sender = 0;
        message->dest_id = graph->partition->placement(i);
        int pe_id = graph->partition->pe_id(graph->partition->placement(i));
        message->dest_pe = pe_id;
        message->dest_fpga = 0;
        message->roundpar = 3;
        message->barrier = false;
        message->payload.weight = 0.15/graph->nv;
        message->timestamp = 0;
        pe[pe_id]->putMessageToReceive(message);
        sent[pe_id]++;
    }
}
