#pragma once

#include "baseapplykernel.h"
#include "Vgatherapply.h"

class RelaxedHWApplyKernel : public BaseApplyKernel {
    void do_init();
protected:
    Vgatherapply * ga_hw;
    int num_in_use;
    virtual void setStateInput(VertexData* vertex) = 0;
    virtual void setMessageInput(Message* message) = 0;
    virtual void getStateOutput(VertexData* vertex) = 0;
    virtual void getUpdatePayload(Update* update) = 0;
    virtual void resetStateInput() = 0;
    virtual void vertexCheckoutPrint();
    virtual void vertexWritebackPrint();
public:
    RelaxedHWApplyKernel(int pe_id, vertexid_t num_vertices, Graph* graph);
    virtual ~RelaxedHWApplyKernel();
    void tick();
    void barrier(Message* bm);
};
