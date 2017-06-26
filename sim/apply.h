#include "applykernel.h"
#include "format_def.h"


class Apply {
    int level;
    ApplyKernel* applykernel;
    void verifyIncomingMessage(Message* message);
public:
    Apply(int num_vertices);
    Apply(VertexData* init_data, int num_vertices);
    ~Apply();
    Update* receiveMessage(Message* message);
};
