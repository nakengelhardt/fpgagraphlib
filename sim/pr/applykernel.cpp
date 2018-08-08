#include "applykernel.h"
#include <iostream>

void ApplyKernel::setStateInputGather(VertexData* vertex){
    gather_hw->state_in_nneighbors = vertex->nneighbors;
    gather_hw->state_in_nrecvd = vertex->nrecvd;
    *((float*) &gather_hw->state_in_sum) = vertex->sum;
    gather_hw->state_in_active = vertex->active;
}

void ApplyKernel::setMessageInputGather(Message* message){
    *((float*) &gather_hw->message_in_weight) = message->payload.weight;
}

void ApplyKernel::getStateOutputGather(VertexData* vertex){
    vertex->nneighbors = gather_hw->state_out_nneighbors;
    vertex->nrecvd = gather_hw->state_out_nrecvd;
    vertex->sum = *((float*) &gather_hw->state_out_sum);
    vertex->active = gather_hw->state_out_active;
}

void ApplyKernel::setStateInputApply(VertexData* vertex){
    apply_hw->state_in_nneighbors = vertex->nneighbors;
    apply_hw->state_in_nrecvd = vertex->nrecvd;
    *((float*) &apply_hw->state_in_sum) = vertex->sum;
    apply_hw->state_in_active = vertex->active;
}

void ApplyKernel::resetStateInputApply(){
    apply_hw->state_in_nneighbors = 0;
    apply_hw->state_in_nrecvd = 0;
    apply_hw->state_in_sum = 0;
    apply_hw->state_in_active = 0;
}

void ApplyKernel::getStateOutputApply(VertexData* vertex){
    if(apply_hw->state_out_nneighbors != vertex->nneighbors
      || apply_hw->state_out_nrecvd != 0
      || apply_hw->state_out_sum != 0
      || apply_hw->state_out_active != 0) {
        std::cout << "Apply not resetting state properly:" << std::endl;
        std::cout << "apply_hw->state_out_nneighbors = " << apply_hw->state_out_nneighbors
        << " (" << vertex->nneighbors << ")"
        << ", apply_hw->state_out_nrecvd = " << apply_hw->state_out_nrecvd
        << ", apply_hw->state_out_sum = " << apply_hw->state_out_sum
        << ", apply_hw->state_out_active = " << apply_hw->state_out_active
        << std::endl;

    }
    vertex->sum = 0;
    vertex->nrecvd = 0;
}

void ApplyKernel::getUpdatePayload(Update* update){
    update->payload.weight = *((float*) &apply_hw->update_out_weight);
}

void ApplyKernel::vertexCheckoutPrint(){
    std::cout << "Checkout vertex " << gather_hw->nodeid_in
    << ": nneighbors=" << gather_hw->state_in_nneighbors
    << ", nrecvd=" << gather_hw->state_in_nrecvd
    << ", sum=" << *((float*) &gather_hw->state_out_sum)
    << ", message add " << *((float*) &gather_hw->message_in_weight)
    << ", now in use: " << num_in_use_gather
    << std::endl;
}

void ApplyKernel::vertexWritebackPrint(VertexEntry* vertex){
    std::cout << "Writeback vertex " << gather_hw->nodeid_out
    << ": " << "nneighbors " << vertex->data.nneighbors << " -> " << gather_hw->state_out_nneighbors
    << ", nrecvd " << vertex->data.nrecvd << " -> " << gather_hw->state_out_nrecvd
    << ", sum " << vertex->data.sum << " -> " << *((float*) &gather_hw->state_out_sum)
    << ", remaining in use: " << num_in_use_gather
    << std::endl;
}

void ApplyKernel::printState(){
    for(int i = 0; i < num_vertices; i++){
        if (pe_id != 0 or i != 0) {
            std::cout << vertex_data[i].id ;
            if(vertex_data[i].data.active){
                std::cout << "*";
            } else {
                std::cout << " ";
            }
            std::cout << "{" << vertex_data[i].data.nrecvd << "/" << vertex_data[i].data.nneighbors
            << ", " << vertex_data[i].data.sum << "}" << std::endl;
        }
    }
}
