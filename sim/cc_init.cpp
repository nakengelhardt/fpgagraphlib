#include "format_def.h"
#include "pe.h"
#include "graph.h"

#ifdef CC

void initVertexData(VertexData* init_data, vertexid_t vertex, int index, Graph* graph){
    init_data[index].color = 0x3FFFFFFF;
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
        message->payload.color = message->dest_id;
        message->timestamp = 0;
        pe[pe_id]->putMessageToReceive(message);
        sent[pe_id]++;
    }
}

#endif
