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

class ScatterKernel {
    int num_vertices;
    SCATTER_HW* scatter_hw;
    std::queue<ScatterKernelInput> inputQ;
    TimeStation timestamp_in;
    int* last_input_time;
    int latency;
    void setInput(ScatterKernelInput input);
    void getOutput(Message* message);
public:
    ScatterKernel(int num_vertices);
    ~ScatterKernel();
    void queue(Update* update, edge_t edge, vertexid_t num_neighbors, bool last);
    Message* tick();
};
