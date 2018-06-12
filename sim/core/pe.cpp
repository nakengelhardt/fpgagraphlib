#include "pe.h"

#include <iostream>

int PE::num_updates = 0;

PE::PE(Apply* apply, Scatter* scatter) : apply(apply), scatter(scatter) {
    timestamp_out = 0;
}

PE::~PE() {
    delete apply;
    delete scatter;
}

void PE::tick() {
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
        } else {
            num_updates++;
            #ifdef SIM_DEBUG
            std::cout << "Update from vertex " << update->sender << std::endl;
            #endif
        }
    }

    message = scatter->receiveUpdate(update);
    if (message) {
        outputQ.push(message);
    }
}

Message* PE::getSentMessage(int roundpar) {
    Message* message = NULL;
    if (!outputQ.empty() && outputQ.front()->roundpar == roundpar) {
        message = outputQ.front();
        if(timestamp_out < message->timestamp){
            timestamp_out = message->timestamp;
        }
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
    return timestamp_out;
}
