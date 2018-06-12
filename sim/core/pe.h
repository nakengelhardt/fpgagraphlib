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
    static int num_updates;
    PE(Apply* apply, Scatter* scatter);
    ~PE();
    void tick();
    Message* getSentMessage(int roundpar);
    void putMessageToReceive(Message* message);
    int getTime();
};
