#pragma once

#include "timestamp.h"
#include "format_def.h"
#include <queue>

struct ScatterKernelInput{
    Update* update;
    edge_t edge;
    vertexid_t num_neighbors;
    bool last;
};

class BaseScatterKernel {
protected:
    std::queue<ScatterKernelInput> inputQ;
public:
    virtual ~BaseScatterKernel() {};
    void queue(Update* update, edge_t edge, vertexid_t num_neighbors, bool last);
    virtual Message* tick() = 0;
};
