#include "applykernel.h"
#include <iostream>

Update* ApplyKernel::gatherapply(Message* message, VertexEntry* vertex, int level) {
    Update* update = NULL;
    if (message) {
        if(!message->barrier){ // gather
            if (message->payload.hops < 2) {
                #ifdef APP_DEBUG
                    std::cout << "Level " << level << ": Forwarding message from " << message->payload.origin << std::endl;
                #endif
                update = new Update();
                update->payload = message->payload;
                if (update->payload.hops == 0){
                    update->payload.via_1 = vertex->id;
                }
                if (update->payload.hops == 1) {
                    update->payload.via_2 = vertex->id;
                }
                update->payload.hops++;
            } else if (message->payload.hops == 2) {
                if(message->payload.origin == vertex->id) {
                    vertex->data.num_triangles++;
                    #ifdef APP_DEBUG
                        std::cout << "Found triangle: " << message->payload.origin << " -- " << message->payload.via_1 << " -- " << message->payload.via_2 << std::endl;
                    #endif
                }
            }
        } else { // apply
            if (vertex->data.active && (level == vertex->data.send_in_level)) {
                #ifdef APP_DEBUG
                    std::cout << "Initial broadcast: " << vertex->id << std::endl;
                #endif
                update = new Update();
                update->payload.origin = vertex->id;
                update->payload.hops = 0;
                vertex->data.active = false;
            }
        }
    }
    return update;
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
            std::cout << "{" << vertex_data[i].data.num_triangles << "}" << std::endl;
        }
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
