#include "init.h"


void initVertexData(VertexEntry* init_data, vertexid_t vertex, Graph* graph){
    init_data->data.parent = 0;
}

void sendInitMessages(Graph* graph, PE** pe, int* sent){
    vertexid_t root_vertex = 0;
    Message* message;
    message = new Message();
    message->dest_id = graph->partition->placement(root_vertex);
    message->sender = message->dest_id;
    int pe_id = graph->partition->pe_id(graph->partition->placement(root_vertex));
    message->dest_pe = pe_id;
    message->dest_fpga = pe_id % num_fpga;
    message->roundpar = 3;
    message->barrier = false;
    message->timestamp = 0;
    pe[pe_id]->putMessageToReceive(message);
    sent[pe_id]++;
}
