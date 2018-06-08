#pragma once

#include "baseapplykernel.h"
#include "format_def.h"


class Apply {
    int level;
    int update_level;
    BaseApplyKernel* applykernel;
    void verifyIncomingMessage(Message* message);
public:
    Apply(BaseApplyKernel* a);
    ~Apply();
    Update* receiveMessage(Message* message);
};
