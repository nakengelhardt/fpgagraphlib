#include "format_def.h"
#include "Vpr_apply.h"
#include <queue>

struct ApplyKernelInput{
    Message* message;
    VertexData* vertex;
    int level;
};

class ApplyKernel {
    VertexData * vertex_data;
    Vpr_apply* top;
    void do_reset();
public:
    int num_vertices;
    std::queue<ApplyKernelInput> inputQ;
    ApplyKernel(int num_vertices);
    ApplyKernel(VertexData* init_data, int num_vertices);
    ~ApplyKernel();
    VertexData* getDataRef(vertexid_t vertex);
    void queueInput(Message* message, VertexData* vertex, int level);
    Update* tick();
    void printState();
};
