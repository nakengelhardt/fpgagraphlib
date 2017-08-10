#pragma once

#include "scatterkernel.h"
#include "graph.h"

class Scatter {
    ScatterKernel* scatterkernel;
    Graph* graph;
    int in_level;
    int out_level;
public:
    Scatter(Graph* graph);
    ~Scatter();
    std::queue<Update*> updateQ;
    Message* receiveUpdate(Update* update);
};
