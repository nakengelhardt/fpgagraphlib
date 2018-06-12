#pragma once

#include "swapplykernel.h"
#include "graph.h"
#include "pe.h"

class ApplyKernel : public SWApplyKernel {
    // void gather(Message* message, VertexEntry* vertex, int level);
    // Update* apply(VertexEntry* vertex, int level);
    Update* gatherapply(Message* message, VertexEntry* vertex, int level);
public:
    static int total_triangles;
    ApplyKernel(int pe_id, vertexid_t num_vertices, Graph* graph) : SWApplyKernel(pe_id, num_vertices, graph) {};
    ~ApplyKernel();
    void printState();
    int countTriangles();
};
