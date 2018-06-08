#pragma once

#include "basescatterkernel.h"
#include "timestamp.h"

class SWScatterKernel : public BaseScatterKernel {
    int num_vertices;
    TimeStation timestamp_in;
    int* last_input_time;
    int latency;
protected:
    virtual Message* scatter(Update* update, edge_t edge, vertexid_t num_neighbors) = 0;
public:
    SWScatterKernel(int pe_id, vertexid_t num_vertices);
    virtual ~SWScatterKernel();
    Message* tick();
};
