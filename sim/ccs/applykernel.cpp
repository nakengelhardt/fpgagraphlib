#include "applykernel.h"
#include <iostream>

void ApplyKernel::gather(Message* message, VertexEntry* vertex, int level) {
    if (vertex->data.color > message->payload.color) {
        #ifdef SIM_DEBUG
            std::cout << "Gather: " << vertex->id << " updated with color " << message->payload.color << "( old color: " << vertex->data.color << ")" << std::endl;
        #endif
        vertex->data.color = message->payload.color;
        vertex->data.active = 1;
    }
}

Update* ApplyKernel::apply(VertexEntry* vertex, int level) {
    if (vertex->data.active) {
        vertex->data.active = 0;
        #ifdef SIM_DEBUG
            std::cout << "Apply: " << vertex->id << " broadcasts new color " << vertex->data.color << std::endl;
        #endif
        Update* update = new Update;
        update->payload.color = vertex->data.color;
        return update;
    }
    return NULL;
}

// Update* ApplyKernel::gatherapply(Message* message, VertexEntry* vertex, int level) {
//     Update* update = NULL;
//     if (message) {
//         if(!message->barrier){ // gather
//             if (vertex->data.color > message->payload.color) {
//                 #ifdef APP_DEBUG
//                     std::cout << "Gather: " << vertex->id << " updated with color " << message->payload.color << "( old color: " << vertex->data.color << ")" << std::endl;
//                 #endif
//                 vertex->data.color = message->payload.color;
//                 vertex->active = 1;
//             }
//         } else { // apply
//             if (vertex->active) {
//                 vertex->active = 0;
//                 #ifdef APP_DEBUG
//                     std::cout << "Apply: " << vertex->id << " broadcasts new color " << vertex->data.color << std::endl;
//                 #endif
//                 update = new Update;
//                 update->payload.color = vertex->data.color;
//             }
//         }
//     }
//     return update;
// }

void ApplyKernel::printState(){
    for(int i = 0; i < num_vertices; i++){
        if (pe_id != 0 or i != 0) {
            std::cout << vertex_data[i].id ;
            if(vertex_data[i].data.active){
                std::cout << "*";
            } else {
                std::cout << " ";
            }
            std::cout << "{" << vertex_data[i].data.color << "}" << std::endl;
        }
    }
}
