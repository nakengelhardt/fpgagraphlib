#pragma once

#include "baseapplykernel.h"

class SWApplyKernel : public BaseApplyKernel {
protected:
    TimeStation timestamp_in;
    TimeStation timestamp_out;
    int latency;
    int* last_input_time;
    virtual void gather(Message* message, VertexEntry* vertex, int level) = 0;
    virtual Update* apply(VertexEntry* vertex, int level) = 0;
public:
    SWApplyKernel(int pe_id, vertexid_t num_vertices, Graph* graph);
    virtual ~SWApplyKernel();
    void gather_tick();
    void apply_tick();
    void barrier(Message* bm);
    virtual void printState() = 0;
};
