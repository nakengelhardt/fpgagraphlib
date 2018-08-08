#pragma once

#include "basescatterkernel.h"
#include "Vscatter.h"

class HWScatterKernel : public BaseScatterKernel {
protected:
    int num_vertices;
    Vscatter* scatter_hw;
    virtual void setInput(ScatterKernelInput input) = 0;
    virtual void getOutput(Message* message) = 0;
public:
    HWScatterKernel(int pe_id, vertexid_t num_vertices);
    virtual ~HWScatterKernel();
    Message* tick();
};
