#pragma once

#include "graph.h"
#include "format_def.h"
#include <queue>

struct ApplyKernelInput{
    Message* message;
    VertexEntry* vertex;
    int level;
};

class BaseApplyKernel {
protected:
    int pe_id;
    Graph* graph;
    std::queue<ApplyKernelInput> inputQ;
    std::queue<Update*> outputQ;
    VertexEntry* vertex_data;
public:
    int num_vertices;
    BaseApplyKernel(int pe_id, vertexid_t num_vertices, Graph* graph);
    virtual ~BaseApplyKernel();
    VertexEntry* getVertexEntry(vertexid_t vertex);
    VertexEntry* getLocalVertexEntry(int vertex);
    void queueInput(Message* message, VertexEntry* vertex, int level);
    Update* getUpdate();
    virtual void gather_tick() = 0;
    virtual void apply_tick() = 0;
    virtual void barrier(Message* bm) = 0;
    virtual void printState();
};
