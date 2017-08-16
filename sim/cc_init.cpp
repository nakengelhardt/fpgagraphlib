#include "format_def.h"
#include "pe.h"
#include "graph.h"

#ifdef CC

void initVertexData(VertexData* init_data, vertexid_t vertex, int index, Graph* graph){
    init_data[index].color = 0x3FFFFFFF;
}

void sendInitMessages(Graph* graph, PE** pe, int* sent){
    Message* message;
    message = new Message();
    message->dest_id = graph->partition->placement(1);
    message->sender = message->dest_id;
    message->color = message->dest_id;
    int pe_id = graph->partition->pe_id(graph->partition->placement(1));
    message->dest_pe = pe_id;
    message->dest_fpga = pe_id % num_fpga;
    message->roundpar = 3;
    message->barrier = false;
    message->timestamp = 0;
    pe[pe_id]->putMessageToReceive(message);
    sent[pe_id]++;
}

#endif
