#pragma once

#include "basescatterkernel.h"
#include "graph.h"

class Scatter {
    BaseScatterKernel* scatterkernel;
    Graph* graph;
    int in_level;
    int out_level;
public:
    Scatter(Graph* graph, BaseScatterKernel* s);
    ~Scatter();
    std::queue<Update*> updateQ;
    Message* receiveUpdate(Update* update);
};
