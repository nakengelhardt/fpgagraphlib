#pragma once

#include "apply.h"
#include "scatter.h"

#include <queue>

class PE {
    Apply* apply;
    Scatter* scatter;
    std::queue<Message*> inputQ;
    std::queue<Message*> outputQ;
    int num_ticks;
    int num_messages;
    int num_updates;
public:
    int last_completed_superstep_updates;
    int last_completed_superstep_messages;
    PE(Apply* apply, Scatter* scatter);
    ~PE();
    void tick();
    Message* getSentMessage(int roundpar);
    void putMessageToReceive(Message* message);
    int getTime();
};
