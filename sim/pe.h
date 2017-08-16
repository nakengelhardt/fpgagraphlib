#pragma once

#include "apply.h"
#include "scatter.h"

#include <queue>

class PE {
    Apply* apply;
    Scatter* scatter;
    std::queue<Message*> inputQ;
    std::queue<Message*> outputQ;
    int timestamp_out;
public:
    PE(Apply* apply, Scatter* scatter);
    void tick();
    Message* getSentMessage();
    void putMessageToReceive(Message* message);
    int getTime();
};
