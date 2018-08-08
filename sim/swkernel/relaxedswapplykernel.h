#pragma once

#include "baseapplykernel.h"

class RelaxedSWApplyKernel : public BaseApplyKernel {
protected:
    int level;
    // virtual void gather(Message* message, VertexEntry* vertex, int level) = 0;
    // virtual Update* apply(VertexEntry* vertex, int level) = 0;
    virtual Update* gatherapply(Message* message, VertexEntry* vertex, int level) = 0;
public:
    RelaxedSWApplyKernel(int pe_id, vertexid_t num_vertices, Graph* graph);
    virtual ~RelaxedSWApplyKernel();
    void tick();
    void barrier(Message* bm);
    virtual void printState() = 0;
};
