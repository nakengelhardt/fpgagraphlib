#include "scatterkernel.h"

#include <iostream>

Message* ScatterKernel::scatter(Update* update, edge_t edge, vertexid_t num_neighbors){
    if (update->payload.hops < 2){
        if (edge.dest_degree < 2)
            return NULL;
        if (num_neighbors < edge.dest_degree)
            return NULL;
        if (num_neighbors == edge.dest_degree && update->sender > edge.dest_id)
            return NULL;
        if(edge.dest_id == update->payload.origin)
            return NULL;
    } else {
        if(edge.dest_id != update->payload.origin)
            return NULL;
    }
    Message* message = new Message();
    message->payload = update->payload;
    return message;
}
