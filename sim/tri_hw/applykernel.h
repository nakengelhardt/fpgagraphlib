#pragma once

#include "relaxedhwapplykernel.h"
#include "graph.h"
#include "pe.h"

class ApplyKernel : public RelaxedHWApplyKernel {
    void setStateInput(VertexData* vertex);
    void setMessageInput(Message* message);
    void getStateOutput(VertexData* vertex);
    void getUpdatePayload(Update* update);
    void resetStateInput();
public:
    static int total_triangles;
    ApplyKernel(int pe_id, vertexid_t num_vertices, Graph* graph) : RelaxedHWApplyKernel(pe_id, num_vertices, graph) {};
    ~ApplyKernel();
    void printState();
    int countTriangles();
};
