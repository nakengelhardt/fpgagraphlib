#pragma once

#include "format_def.h"
#include "pr_scatterkernel.h"
#include <queue>

struct ScatterKernelInput{
    Update* update;
    edge_t edge;
    vertexid_t num_neighbors;
    bool last;
};

class ScatterKernel {
    SCATTER_HW* scatter_hw;
    std::queue<ScatterKernelInput> inputQ;
    void setInput(ScatterKernelInput input);
    void getOutput(Message* message);
public:
    ScatterKernel();
    ~ScatterKernel();
    void queue(Update* update, edge_t edge, vertexid_t num_neighbors, bool last);
    Message* tick();
};
