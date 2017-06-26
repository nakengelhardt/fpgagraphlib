#include "scatter.h"
#include <iostream>

Scatter::Scatter(Graph* g){
    graph = g;
    scatterkernel = new ScatterKernel();
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
    return scatterkernel->tick();
}
