#include "applykernel.h"
#include <iostream>


void ApplyKernel::setStateInput(VertexData* vertex){
    ga_hw->state_in_send_in_level = vertex->send_in_level;
    ga_hw->state_in_num_triangles = vertex->num_triangles;
    ga_hw->state_in_active = vertex->active;
}

void ApplyKernel::setMessageInput(Message* message){
    ga_hw->message_in_origin = message->payload.origin;
    ga_hw->message_in_hops = message->payload.hops;
}

void ApplyKernel::resetStateInput(){
    ga_hw->state_in_send_in_level = 0;
    ga_hw->state_in_num_triangles = 0;
    ga_hw->state_in_active = 0;
}

void ApplyKernel::getStateOutput(VertexData* vertex){
    if(ga_hw->state_out_send_in_level != vertex->send_in_level) {
        std::cout << "Apply not resetting state properly:" << std::endl;
        std::cout << "ga_hw->state_out_send_in_level = " << ga_hw->state_out_send_in_level
        << " (" << vertex->send_in_level << ")"
        << std::endl;
    }
    vertex->num_triangles = ga_hw->state_out_num_triangles;
    vertex->active = ga_hw->state_out_active;
}

void ApplyKernel::getUpdatePayload(Update* update){
    update->payload.origin = ga_hw->update_out_origin;
    update->payload.hops = ga_hw->update_out_hops;
}

void ApplyKernel::printState(){
    for(int i = 0; i < num_vertices; i++){
        std::cout << vertex_data[i].id;
        if(vertex_data[i].data.active){
            std::cout << "*";
        } else {
            std::cout << " ";
        }
        std::cout << " {" << vertex_data[i].data.num_triangles << "}" << std::endl;
    }
}

int ApplyKernel::total_triangles = 0;

int ApplyKernel::countTriangles(){
    int num_triangles = 0;
    for(int i = 0; i < num_vertices; i++){
        if (pe_id != 0 or i != 0) {
            num_triangles += vertex_data[i].data.num_triangles;
        }
    }
    return num_triangles;
}

ApplyKernel::~ApplyKernel() {
    int num_triangles = countTriangles();
    total_triangles += num_triangles;
}
