#include "applykernel.h"
#include <iostream>

void ApplyKernel::setStateInputGather(VertexData* vertex){
    gather_hw->state_in_dist = vertex->dist;
    gather_hw->state_in_parent = vertex->parent;
}

void ApplyKernel::setMessageInputGather(Message* message){
    gather_hw->message_in_dist = message->payload.dist;
}

void ApplyKernel::getStateOutputGather(VertexData* vertex){
    vertex->dist = gather_hw->state_out_dist;
    vertex->parent = gather_hw->state_out_parent;
}

void ApplyKernel::setStateInputApply(VertexData* vertex){
    apply_hw->state_in_dist = vertex->dist;
    apply_hw->state_in_parent = vertex->parent;
}

void ApplyKernel::resetStateInputApply(){
    apply_hw->state_in_dist = 0;
    apply_hw->state_in_parent = 0;
}

void ApplyKernel::getStateOutputApply(VertexData* vertex){
    if(apply_hw->state_out_dist != vertex->dist
      || apply_hw->state_out_parent != vertex->parent
      || apply_hw->state_out_active != 0) {
        std::cout << "Apply not resetting state properly:" << std::endl;
        std::cout << "apply_hw->state_out_dist = " << apply_hw->state_out_dist
        << " (" << vertex->dist << ")"
        << ", apply_hw->state_out_parent = " << apply_hw->state_out_parent
        << ", apply_hw->state_out_active = " << apply_hw->state_out_active
        << std::endl;
    }
}

void ApplyKernel::getUpdatePayload(Update* update){
    update->payload.dist = apply_hw->update_out_dist;
}

void ApplyKernel::vertexCheckoutPrint(){
    std::cout << "Checkout vertex " << static_cast<int>(gather_hw->nodeid_in)
    << ": dist=" << static_cast<int>(gather_hw->state_in_dist)
    << ", parent=" << static_cast<int>(gather_hw->state_in_parent)
    << ", message " << static_cast<int>(gather_hw->message_in_dist)
    << ", now in use: " << num_in_use_gather
    << std::endl;
}

void ApplyKernel::vertexWritebackPrint(VertexEntry* vertex){
    std::cout << "Writeback vertex " << static_cast<int>(gather_hw->nodeid_out)
    << ": " << "dist " << vertex->data.dist << " -> " << static_cast<int>(gather_hw->state_out_dist)
    << ", parent " << vertex->data.parent << " -> " << static_cast<int>(gather_hw->state_out_parent)
    << ", remaining in use: " << num_in_use_gather
    << std::endl;
}

void ApplyKernel::printState(){
    for(int i = 0; i < num_vertices; i++){
        if (pe_id != 0 or i != 0) {
            std::cout << vertex_data[i].id;
            if(vertex_data[i].active){
                std::cout << "*";
            } else {
                std::cout << " ";
            }
            std::cout << "{" << vertex_data[i].data.dist << " via "
            << vertex_data[i].data.parent << "}" << std::endl;
        }
    }
}
