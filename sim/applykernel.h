#pragma once

#include "format_def.h"
#include "sssp_applykernel.h"
#include <queue>

struct ApplyKernelInput{
    Message* message;
    VertexData* vertex;
    int level;
};

class ApplyKernel {
    VertexData * vertex_data;
    GATHER_HW * gather_hw;
    APPLY_HW * apply_hw;
    void do_init();
    int num_in_use_gather;
    int num_in_use_apply;
    void setStateInputGather(VertexData* vertex);
    void setMessageInputGather(Message* message);
    void getStateOutputGather(VertexData* vertex);
    void setStateInputApply(VertexData* vertex);
    void resetStateInputApply();
    void getStateOutputApply(VertexData* vertex);
    void getUpdatePayload(Update* update);
    void vertexCheckoutPrint();
    void vertexWritebackPrint(VertexData* vertex);
public:
    int num_vertices;
    std::queue<ApplyKernelInput> inputQ;
    std::queue<Update*> outputQ;
    ApplyKernel(VertexData* init_data, int num_vertices);
    ~ApplyKernel();
    VertexData* getDataRef(vertexid_t vertex);
    void queueInput(Message* message, VertexData* vertex, int level);
    Update* getUpdate();
    void gather_tick();
    void apply_tick();
    void barrier(Message* bm);
    void printState();
};
