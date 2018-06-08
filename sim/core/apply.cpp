#include "apply.h"

#include <stdexcept>
#include <iostream>

Apply::Apply(BaseApplyKernel* a) {
    level = 0;
    update_level = 0;
    applykernel = a;
}

Apply::~Apply() {
    delete applykernel;
}

void Apply::verifyIncomingMessage(Message* message){
    if(!message->barrier && (message->dest_id <= 0 || (message->dest_id & NODEID_MASK) > applykernel->num_vertices)){
        std::cout << "Sending message to nonexistent vertex!" << std::endl;
        throw std::runtime_error("");
    }
    if(message->roundpar != (((level + num_channels - 1) % num_channels))) {
        std::cout << "Message from vertex " << message->sender
        << " of round " << message->roundpar
        << " but expecting " << (level + num_channels - 1) % num_channels
        << " (level = " << level << ")"
        << std::endl;
        throw std::runtime_error("");
    }
}

Update* Apply::receiveMessage(Message* message) {
    if (message) {
        verifyIncomingMessage(message);
        if (message->barrier){
            applykernel->barrier(message);
            level++;
            // std::cout << "Increasing level to " << level << std::endl;
        } else {
            applykernel->queueInput(message, applykernel->getVertexEntry(message->dest_id), level);
        }
    }
    Update* update = applykernel->getUpdate();
    if(update){
        if(update->barrier){
            update_level++;
            if (level != update_level){
                throw std::runtime_error(AT "Too many barriers");
            }

        } else {
            if(update->roundpar != update_level % num_channels) {
                throw std::runtime_error(AT "Superstep order not respected");
            }
        }
    }
    return update;
}
