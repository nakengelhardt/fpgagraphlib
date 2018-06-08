#pragma once

#include "basescatterkernel.h"
#include "timestamp.h"
#include "Vscatter.h"

class HWScatterKernel : public BaseScatterKernel {
protected:
    int num_vertices;
    TimeStation timestamp_in;
    int* last_input_time;
    int scatter_latency;
    int latency;
    Vscatter* scatter_hw;
    virtual void setInput(ScatterKernelInput input) = 0;
    virtual void getOutput(Message* message) = 0;
public:
    HWScatterKernel(int pe_id, vertexid_t num_vertices);
    virtual ~HWScatterKernel();
    Message* tick();
};
