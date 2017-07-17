#include "applykernel.h"

#include <stdexcept>
#include <iostream>

VertexData* ApplyKernel::getDataRef(vertexid_t vertex){
    if (vertex == 0){
        std::cout << "***Accessing Vertex 0***" << std::endl;
    }
    int local_id = vertex & NODEID_MASK;
    return &vertex_data[local_id];
}

ApplyKernel::ApplyKernel(int n) {
    num_vertices = n;
    vertex_data = new VertexData[num_vertices];
    memset(vertex_data, 0, num_vertices*sizeof(VertexData));
}

ApplyKernel::ApplyKernel(VertexData* init_data, int n) {
    num_vertices = n;
    vertex_data = init_data;
}

ApplyKernel::~ApplyKernel() {
}

void ApplyKernel::queueInput(Message* message, VertexData* vertex, int level) {
    ApplyKernelInput input;
    input.message = message;
    input.vertex = vertex;
    input.level = level;
    inputQ.push(input);
}

Update* ApplyKernel::getUpdate(){
    Update* update = NULL;
    if(!outputQ.empty()){
        update = outputQ.front();
        outputQ.pop();
    }
    return update;
}

void ApplyKernel::barrier(Message* bm) {
    Update* update;
    for (int i = 0; i < num_vertices; i++){
        VertexData* vertex = &vertex_data[i];
        if (vertex->active){
            if(vertex->in_use) {
                std::cout << "Vertex " << vertex->id << " has not returned state." << std::endl;
            }
            if(vertex->nrecvd != vertex->nneighbors) {
                std::cout << "Vertex " << vertex->id << " has not received all messages." << std::endl;
            }

            update = new Update;
            update->sender = vertex->id;
            update->roundpar = (bm->roundpar + 1) % num_channels;
            update->barrier = false;
            update->payload.weight = vertex->sum * 0.85 + 0.15/num_vertices;
            outputQ.push(update);

            vertex->sum = 0;
            vertex->nrecvd = 0;
            vertex->active = 0;
        }
    }
    update = new Update;
    update->sender = 0;
    update->roundpar = (bm->roundpar + 1) % num_channels;
    update->barrier = true;
    outputQ.push(update);
}

void ApplyKernel::tick() {
    if(!inputQ.empty()) {
        ApplyKernelInput input = inputQ.front();
        Message* message = input.message;
        VertexData* vertex = input.vertex;
        vertex->active = true;

        if (input.level == 0) {
            vertex->sum = 0;
            vertex->nrecvd = vertex->nneighbors;
        } else if (input.level < 30) {
            vertex->sum += message->payload.weight;
            vertex->nrecvd++;
        } else {
            vertex->active = false;
        }

        delete inputQ.front().message;
        inputQ.pop();
    }

}

void ApplyKernel::printState(){
    for(int i = 0; i < num_vertices; i++){
        std::cout << i ;
        if(vertex_data[i].in_use){
            std::cout << "*";
        } else {
            std::cout << " ";
        }
        std::cout << "{" << vertex_data[i].nrecvd << "/" << vertex_data[i].nneighbors
        << ", " << vertex_data[i].sum << "}" << std::endl;
    }
}
