#pragma once

#include "swscatterkernel.h"

class ScatterKernel : public SWScatterKernel {
    Message* scatter(Update* update, edge_t edge, vertexid_t num_neighbors);
public:
    ScatterKernel(int pe_id, vertexid_t num_vertices) : SWScatterKernel(pe_id, num_vertices) {};
};
