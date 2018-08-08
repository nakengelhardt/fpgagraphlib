#pragma once

#include "baseapplykernel.h"
#include "Vgather.h"
#include "Vapply.h"

class HWApplyKernel : public BaseApplyKernel {
    void do_init();
protected:
    Vgather * gather_hw;
    Vapply * apply_hw;
    int num_in_use_gather;
    int num_in_use_apply;
    virtual void setStateInputGather(VertexData* vertex) = 0;
    virtual void setMessageInputGather(Message* message) = 0;
    virtual void getStateOutputGather(VertexData* vertex) = 0;
    virtual void setStateInputApply(VertexData* vertex) = 0;
    virtual void resetStateInputApply() = 0;
    virtual void getStateOutputApply(VertexData* vertex) = 0;
    virtual void getUpdatePayload(Update* update) = 0;
    virtual void vertexCheckoutPrint();
    virtual void vertexWritebackPrint(VertexEntry* vertex);
    void gather_tick();
    void apply_tick();
public:
    HWApplyKernel(int pe_id, vertexid_t num_vertices, Graph* graph);
    virtual ~HWApplyKernel();
    void tick();
    void barrier(Message* bm);
};
