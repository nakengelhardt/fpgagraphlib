#pragma once

#include "baseapplykernel.h"
#include "Vgather.h"
#include "Vapply.h"

class HWApplyKernel : public BaseApplyKernel {
    void do_init();
protected:
    Vgather * gather_hw;
    int gather_latency;
    Vapply * apply_hw;
    int apply_latency;
    int num_in_use_gather;
    int num_in_use_apply;
    TimeStation timestamp_in;
    TimeStation timestamp_out;
    int latency;
    int* last_input_time;
    virtual void setStateInputGather(VertexData* vertex) = 0;
    virtual void setMessageInputGather(Message* message) = 0;
    virtual void getStateOutputGather(VertexData* vertex) = 0;
    virtual void setStateInputApply(VertexData* vertex) = 0;
    virtual void resetStateInputApply() = 0;
    virtual void getStateOutputApply(VertexData* vertex) = 0;
    virtual void getUpdatePayload(Update* update) = 0;
    virtual void vertexCheckoutPrint();
    virtual void vertexWritebackPrint(VertexEntry* vertex);
public:
    HWApplyKernel(int pe_id, vertexid_t num_vertices, Graph* graph);
    virtual ~HWApplyKernel();
    void gather_tick();
    void apply_tick();
    void barrier(Message* bm);
};
