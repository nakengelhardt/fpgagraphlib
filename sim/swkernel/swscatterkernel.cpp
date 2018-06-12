#include "swscatterkernel.h"

#include "format_def.h"

#include <iostream>

SWScatterKernel::SWScatterKernel(int pe_id, vertexid_t num_vertices) : num_vertices(num_vertices) {
    last_input_time = new int[num_vertices];
}

SWScatterKernel::~SWScatterKernel() {
    delete[] last_input_time;
}

Message* SWScatterKernel::tick() {

    if(!inputQ.empty()){
        ScatterKernelInput input = inputQ.front();
        timestamp_in.updateTime(inputQ.front().update->timestamp);
        Message* message = NULL;

        if (input.update->barrier){
            #ifdef SIM_DEBUG
                std::cout << "Scatter barrier" << std::endl;
            #endif
            message = new Message();
        } else {
            message = scatter(input.update, input.edge, input.num_neighbors);
            if(message){
                message->dest_id = input.edge.dest_id;
                message->dest_pe = message->dest_id >> PEID_SHIFT;
            }
        }
        if (message) {
            message->sender = input.update->sender;
            message->roundpar = input.update->roundpar;
            message->barrier = input.update->barrier;
            message->timestamp = timestamp_in.getTime() + latency;
        }
        
        if(inputQ.front().last) {
            delete inputQ.front().update;
        }
        inputQ.pop();

        return message;
    }

    return NULL;
}
