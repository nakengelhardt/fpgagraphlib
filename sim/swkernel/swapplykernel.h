#pragma once

#include "baseapplykernel.h"

class SWApplyKernel : public BaseApplyKernel {
protected:
    int latency;
    int level;
    virtual void gather(Message* message, VertexEntry* vertex, int level) = 0;
    virtual Update* apply(VertexEntry* vertex, int level) = 0;
public:
    SWApplyKernel(int pe_id, vertexid_t num_vertices, Graph* graph);
    virtual ~SWApplyKernel();
    void tick();
    void barrier(Message* bm);
    virtual void printState() = 0;
};
