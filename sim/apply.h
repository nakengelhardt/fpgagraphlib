#pragma once

#include "applykernel.h"
#include "format_def.h"


class Apply {
    int level;
    int update_level;
    ApplyKernel* applykernel;
    void verifyIncomingMessage(Message* message);
public:
    Apply(VertexData* init_data, int num_vertices);
    ~Apply();
    Update* receiveMessage(Message* message);
};
