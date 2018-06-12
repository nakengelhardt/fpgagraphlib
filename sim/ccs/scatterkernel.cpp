#include "scatterkernel.h"

#include <iostream>

Message* ScatterKernel::scatter(Update* update, edge_t edge, vertexid_t num_neighbors){
    Message* message = new Message();
    #ifdef APP_DEBUG
        std::cout << "Scatter to vertex " << edge.dest_id << std::endl;
    #endif
    message->payload.color = update->payload.color;

    return message;
}
