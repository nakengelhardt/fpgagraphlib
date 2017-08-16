#include "applykernel.h"
#include <iostream>

#ifdef BFS

void ApplyKernel::setStateInputGather(VertexData* vertex){
    gather_hw->state_in_parent = vertex->parent;
    gather_hw->state_in_active = vertex->active;
}

void ApplyKernel::setMessageInputGather(Message* message){
}

void ApplyKernel::getStateOutputGather(VertexData* vertex){
    vertex->parent = gather_hw->state_out_parent;
    vertex->active = gather_hw->state_out_active;
}

void ApplyKernel::setStateInputApply(VertexData* vertex){
    apply_hw->state_in_parent = vertex->parent;
    apply_hw->state_in_active = vertex->active;
}

void ApplyKernel::resetStateInputApply(){
    apply_hw->state_in_parent = 0;
    apply_hw->state_in_active = 0;
}

void ApplyKernel::getStateOutputApply(VertexData* vertex){
    if(apply_hw->state_out_parent != vertex->parent
      || apply_hw->state_out_active != 0) {
        std::cout << "Apply not resetting state properly:" << std::endl;
        std::cout << ", apply_hw->state_out_parent = " << apply_hw->state_out_parent
        << ", apply_hw->state_out_active = " << apply_hw->state_out_active
        << std::endl;
    }

    vertex->active = 0;
}

void ApplyKernel::getUpdatePayload(Update* update){
}

void ApplyKernel::vertexCheckoutPrint(){
    std::cout << "Checkout vertex " << static_cast<int>(gather_hw->nodeid_in)
    << ", parent=" << static_cast<int>(gather_hw->state_in_parent)
    << ", message " << static_cast<int>(gather_hw->sender_in)
    << ", now in use: " << num_in_use_gather
    << std::endl;
}

void ApplyKernel::vertexWritebackPrint(VertexData* vertex){
    std::cout << "Writeback vertex " << static_cast<int>(gather_hw->nodeid_out)
    << ", parent " << vertex->parent << " -> " << static_cast<int>(gather_hw->state_out_parent)
    << ", remaining in use: " << num_in_use_gather
    << std::endl;
}

void ApplyKernel::printState(){
    for(int i = 0; i < num_vertices; i++){
        std::cout << i ;
        if(vertex_data[i].active){
            std::cout << "*";
        } else {
            std::cout << " ";
        }
        std::cout << "{Parent: " << vertex_data[i].parent << "}" << std::endl;
    }
}

#endif
