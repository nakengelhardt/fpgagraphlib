#pragma once

#include "pe.h"
#include "graph.h"
#include "hwapplykernel.h"

class ApplyKernel : public HWApplyKernel {
protected:
    void setStateInputGather(VertexData* vertex);
    void setMessageInputGather(Message* message);
    void getStateOutputGather(VertexData* vertex);
    void setStateInputApply(VertexData* vertex);
    void resetStateInputApply();
    void getStateOutputApply(VertexData* vertex);
    void getUpdatePayload(Update* update);
    void vertexCheckoutPrint();
    void vertexWritebackPrint(VertexEntry* vertex);
public:
    ApplyKernel(int pe_id, vertexid_t num_vertices, Graph* graph) : HWApplyKernel(pe_id, num_vertices, graph) {};
    VertexEntry* getVertexEntry(vertexid_t vertex);
    VertexEntry* getLocalVertexEntry(int vertex);
    void printState();
};
