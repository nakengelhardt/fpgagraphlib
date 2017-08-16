#pragma once

#include "format_def.h"

#include <queue>

class Arbiter {
    int pe_id;
    std::queue<Message*> deferredQ;
    std::queue<Message*> outputQ;
    int current_round;
    int* barrier;
    int* num_expected_from_pe;
    int* num_received_from_pe;
    int timestamp_out;
public:
    Arbiter(int pe_id);
    ~Arbiter();
    void putMessage(Message* m);
    Message* getMessage();
};
