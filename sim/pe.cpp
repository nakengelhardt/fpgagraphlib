#include "pe.h"

PE::PE(Apply* apply, Scatter* scatter) : apply(apply), scatter(scatter) {
}

void PE::tick() {
    Message* message = NULL;
    if (!inputQ.empty()) {
        message = inputQ.front();
        inputQ.pop();
    }
    Update* update = apply->receiveMessage(message);

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
