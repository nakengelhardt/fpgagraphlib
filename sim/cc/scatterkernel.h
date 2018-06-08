#pragma once

#include "hwscatterkernel.h"

class ScatterKernel : public HWScatterKernel {
protected:
    void setInput(ScatterKernelInput input);
    void getOutput(Message* message);
public:
    ScatterKernel(int pe_id, vertexid_t num_vertices) : HWScatterKernel(pe_id, num_vertices) {};
};
