#include "pe.h"

#include <iostream>

PE::PE(Apply* apply, Scatter* scatter) : apply(apply), scatter(scatter) {
}

void PE::tick() {
    Message* message = NULL;
    if (!inputQ.empty()) {
        message = inputQ.front();
        inputQ.pop();
    }
    Update* update = apply->receiveMessage(message);
#ifdef DEBUG_PRINT
    if(update){
        if(update->barrier){
            std::cout << "Update barrier" << std::endl;
        } else {
            std::cout << "Update from vertex " << update->sender << std::endl;
        }
    }
#endif
    message = scatter->receiveUpdate(update);
    if (message) {
        outputQ.push(message);
    }
}

Message* PE::getSentMessage() {
    Message* message = NULL;
    if (!outputQ.empty()) {
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
