#include "scatter.h"
#include <iostream>

Scatter::Scatter(Graph* g, BaseScatterKernel* s) {
    graph = g;
    scatterkernel = s;
    in_level = 0;
    out_level = 0;
}

Scatter::~Scatter() {
    delete scatterkernel;
}

Message* Scatter::receiveUpdate(Update* update) {
    if (update) {
        if(update->barrier){
            edge_t edge;
            edge.dest_id = 0;
            scatterkernel->queue(update, edge, 0, true);
            in_level++;
        } else {
            vertexid_t gname = graph->partition->origin(update->sender);
            vertexid_t num_neighbors = graph->num_neighbors(gname);
            for(int i = 0; i < num_neighbors; i++){
                edge_t edge = graph->get_neighbor(gname, i);
                edge.dest_id = graph->partition->placement(edge.dest_id);
                bool last = (i == (num_neighbors - 1));
                scatterkernel->queue(update, edge, num_neighbors, last);
            }
        }
    }
    Message* message = scatterkernel->tick();
    if(message){
        if(message->barrier){
            out_level++;
            if(out_level != in_level){
                throw std::runtime_error(AT "Too many barriers");
            }
        } else if(message->roundpar != out_level % num_channels) {
            throw std::runtime_error(AT "Superstep order not respected");
        }
    }
    return message;
}
