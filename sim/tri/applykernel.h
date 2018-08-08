#pragma once

#include "relaxedswapplykernel.h"
#include "graph.h"
#include "pe.h"

class ApplyKernel : public RelaxedSWApplyKernel {
    Update* gatherapply(Message* message, VertexEntry* vertex, int level);
public:
    static int total_triangles;
    ApplyKernel(int pe_id, vertexid_t num_vertices, Graph* graph) : RelaxedSWApplyKernel(pe_id, num_vertices, graph) {};
    ~ApplyKernel();
    void printState();
    int countTriangles();
};
