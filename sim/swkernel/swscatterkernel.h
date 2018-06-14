#pragma once

#include "basescatterkernel.h"

class SWScatterKernel : public BaseScatterKernel {
    int num_vertices;
protected:
    virtual Message* scatter(Update* update, edge_t edge, vertexid_t num_neighbors) = 0;
public:
    SWScatterKernel(int pe_id, vertexid_t num_vertices);
    virtual ~SWScatterKernel();
    Message* tick();
};
