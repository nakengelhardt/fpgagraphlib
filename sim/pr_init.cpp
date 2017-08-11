#include "format_def.h"
#include "pe.h"
#include "graph.h"


#ifdef PR

void initVertexData(VertexData* init_data, int i, Graph* graph){
    init_data[i].nneighbors = graph->num_neighbors(i);
    init_data[i].nrecvd = 0;
    init_data[i].sum = 0.0;
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
        pe[pe_id]->putMessageToReceive(message);
        sent[pe_id]++;
    }
}

#endif
