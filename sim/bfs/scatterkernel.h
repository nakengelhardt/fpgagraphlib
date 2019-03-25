#pragma once

#include "hwscatterkernel.h"

class ScatterKernel : public HWScatterKernel {
protected:
    void setInput(Update* update, edge_t edge, vertexid_t num_neighbors);
    void getOutput(Message* message);
public:
    ScatterKernel(int pe_id, vertexid_t num_vertices) : HWScatterKernel(pe_id, num_vertices) {};
};
