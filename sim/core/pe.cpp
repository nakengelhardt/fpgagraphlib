#include "pe.h"

#include <iostream>

PE::PE(Apply* apply, Scatter* scatter) : apply(apply), scatter(scatter) {
    num_ticks = 0;
    num_messages = 0;
    num_updates = 0;
    last_completed_superstep_updates = 0;
    last_completed_superstep_messages = 0;
}

PE::~PE() {
    delete apply;
    delete scatter;
}

void PE::tick() {
    num_ticks++;
    Message* message = NULL;
    if (!inputQ.empty()) {
        message = inputQ.front();
        inputQ.pop();
    }
    Update* update = apply->receiveMessage(message);

    if(update){
        if(update->barrier){
            #ifdef SIM_DEBUG
            std::cout << "Update barrier" << std::endl;
            #endif
            last_completed_superstep_updates = num_updates;
            num_updates = 0;
        } else {
            num_updates++;
            #ifdef SIM_DEBUG
            std::cout << "Update from vertex " << update->sender << std::endl;
            #endif
        }
    }

    message = scatter->receiveUpdate(update);
    if (message) {
        if (message->barrier){
            last_completed_superstep_messages = num_messages;
            num_messages = 0;
        } else {
            num_messages++;
        }
        outputQ.push(message);
    }
}

Message* PE::getSentMessage(int roundpar) {
    Message* message = NULL;
    if (!outputQ.empty() && outputQ.front()->roundpar == roundpar) {
        message = outputQ.front();
        outputQ.pop();
    }
    return message;
}

void PE::putMessageToReceive(Message* message){
    if (message) {
        inputQ.push(message);
    }
}

int PE::getTime() {
    return num_ticks;
}
