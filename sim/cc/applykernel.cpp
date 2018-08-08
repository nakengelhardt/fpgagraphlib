#include "applykernel.h"
#include <iostream>


void ApplyKernel::setStateInputGather(VertexData* vertex){
    gather_hw->state_in_color = vertex->color;
    gather_hw->state_in_active = vertex->active;
}

void ApplyKernel::setMessageInputGather(Message* message){
    gather_hw->message_in_color = message->payload.color;
}

void ApplyKernel::getStateOutputGather(VertexData* vertex){
    vertex->color = gather_hw->state_out_color;
    vertex->active = gather_hw->state_out_active;
}

void ApplyKernel::setStateInputApply(VertexData* vertex){
    apply_hw->state_in_color = vertex->color;
    apply_hw->state_in_active = vertex->active;
}

void ApplyKernel::resetStateInputApply(){
    apply_hw->state_in_color = 0;
    apply_hw->state_in_active = 0;
}

void ApplyKernel::getStateOutputApply(VertexData* vertex){
    if(apply_hw->state_out_color != vertex->color
      || apply_hw->state_out_active != 0) {
        std::cout << "Apply not resetting state properly:" << std::endl;
        std::cout << "apply_hw->state_out_color = " << apply_hw->state_out_color
        << " (" << vertex->color << ")"
        << ", apply_hw->state_out_active = " << apply_hw->state_out_active
        << std::endl;
    }
    vertex->color = apply_hw->state_out_color;
    vertex->active = apply_hw->state_out_active;
}

void ApplyKernel::getUpdatePayload(Update* update){
    update->payload.color = apply_hw->update_out_color;
}

void ApplyKernel::vertexCheckoutPrint(){
    std::cout << "Checkout vertex " << static_cast<int>(gather_hw->nodeid_in)
    << ": color=" << static_cast<int>(gather_hw->state_in_color)
    << ", message " << static_cast<int>(gather_hw->message_in_color)
    << ", now in use: " << num_in_use_gather
    << std::endl;
}

void ApplyKernel::vertexWritebackPrint(VertexEntry* vertex){
    std::cout << "Writeback vertex " << static_cast<int>(gather_hw->nodeid_out)
    << ": " << "color " << vertex->data.color << " -> " << static_cast<int>(gather_hw->state_out_color)
    << ", remaining in use: " << num_in_use_gather
    << std::endl;
}

void ApplyKernel::printState(){
    for(int i = 0; i < num_vertices; i++){
        if (pe_id != 0 or i != 0) {
            std::cout << i ;
            if(vertex_data[i].data.active){
                std::cout << "*";
            } else {
                std::cout << " ";
            }
            std::cout << "{" << vertex_data[i].data.color << "}" << std::endl;
        }
    }
}
