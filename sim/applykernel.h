#include "format_def.h"
#include "Vpr_gather.h"
#include "Vpr_apply.h"
#include <queue>

struct ApplyKernelInput{
    Message* message;
    VertexData* vertex;
    int level;
};

class ApplyKernel {
    VertexData * vertex_data;
    Vpr_gather* gather_hw;
    Vpr_apply* apply_hw;
    void do_init();
    int num_in_use_gather;
    int num_in_use_apply;
public:
    int num_vertices;
    std::queue<ApplyKernelInput> inputQ;
    std::queue<Update*> outputQ;
    ApplyKernel(int num_vertices);
    ApplyKernel(VertexData* init_data, int num_vertices);
    ~ApplyKernel();
    VertexData* getDataRef(vertexid_t vertex);
    void queueInput(Message* message, VertexData* vertex, int level);
    Update* getUpdate();
    void gather_tick();
    void apply_tick();
    void barrier(Message* bm);
    void printState();
};
