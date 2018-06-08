#include "baseapplykernel.h"
#include "init.h"

#include <stdexcept>
#include <iostream>

BaseApplyKernel::BaseApplyKernel(int pe_id, vertexid_t num_vertices, Graph* graph) : pe_id(pe_id), graph(graph), num_vertices(num_vertices) {
    vertex_data = new VertexEntry[num_vertices];

    for(int i = 0; i < num_vertices; i++){
        vertexid_t vertex = graph->partition->origin(pe_id, i);
        vertex_data[i].id = 0;
        vertex_data[i].in_use = false;
        vertex_data[i].active = false;
        if ( vertex < graph->nv && vertex >= 0 ) {
            vertex_data[i].id = graph->partition->placement(vertex);
            initVertexData(&vertex_data[i], i, graph);
        }
    }
}

BaseApplyKernel::~BaseApplyKernel() {
    delete[] vertex_data;
}

VertexEntry* BaseApplyKernel::getVertexEntry(vertexid_t vertex){
    if (vertex == 0){
        std::cout << "***Accessing Vertex 0***" << std::endl;
    }
    if (vertex >> PEID_SHIFT != pe_id) {
        std::cout << "***Accessing data of vertex at wrong PE***" << std::endl;
    }
    return &vertex_data[graph->partition->local_id(vertex)];
}

VertexEntry* BaseApplyKernel::getLocalVertexEntry(int vertex){
    return &vertex_data[vertex];
}

void BaseApplyKernel::queueInput(Message* message, VertexEntry* vertex, int level) {
    ApplyKernelInput input;
    input.message = message;
    input.vertex = vertex;
    input.level = level;
    inputQ.push(input);
    gather_tick();
}

Update* BaseApplyKernel::getUpdate(){
    gather_tick();
    apply_tick();
    Update* update = NULL;
    if(!outputQ.empty()){
        update = outputQ.front();
        outputQ.pop();
    }
    return update;
}

void BaseApplyKernel::printState(){
    for(int i = 0; i < num_vertices; i++){
        if (pe_id != 0 or i != 0) {
            std::cout << vertex_data[i].id ;
            if(vertex_data[i].active){
                std::cout << "*";
            } else {
                std::cout << " ";
            }
            std::cout << std::endl;
        }
    }
}
