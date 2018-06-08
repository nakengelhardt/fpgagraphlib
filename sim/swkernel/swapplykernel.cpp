#include "swapplykernel.h"

#include <iostream>

SWApplyKernel::SWApplyKernel(int pe_id, vertexid_t num_vertices, Graph* graph) : BaseApplyKernel(pe_id, num_vertices, graph){
    last_input_time = new int[num_vertices];
}

SWApplyKernel::~SWApplyKernel() {
    delete[] last_input_time;
}

void SWApplyKernel::gather_tick() {
    if(!inputQ.empty()) {
        timestamp_in.incrementTime(1);
        ApplyKernelInput input = inputQ.front();

        gather(input.message, input.vertex, input.level);

        timestamp_in.updateTime(input.message->timestamp);

        delete input.message;
        inputQ.pop();
    }
}



void SWApplyKernel::apply_tick() {

}

void SWApplyKernel::barrier(Message* bm) {
#ifdef DEBUG_PRINT
    std::cout << timestamp_in.getTime() << ": Barrier received, emptying queue" << std::endl;
#endif
    while (!inputQ.empty()) {
        gather_tick();
    }
#ifdef DEBUG_PRINT
    printState();
#endif
    Update* update = NULL;

    int i = 0;
    while (i < num_vertices) {
        VertexEntry* vertex = getLocalVertexEntry(i);
        if (vertex->active){
            last_input_time[i] = timestamp_in.getTime();
            timestamp_in.incrementTime(1);

            update = apply(vertex, (bm->roundpar + 1) % num_channels);

            timestamp_out.updateTime(last_input_time[i]);

            if (update) {
                update->sender = vertex->id;
                update->roundpar = (bm->roundpar + 1) % num_channels;
                update->barrier = false;
                update->timestamp = timestamp_out.getTime();
                outputQ.push(update);
            }

        } else {
            timestamp_in.incrementTime(1);
        }
        i++;
    }

    Update* bu = new Update();
    bu->sender = pe_id << PEID_SHIFT;
    bu->roundpar = (bm->roundpar + 1) % num_channels;
    bu->barrier = true;
    bu->timestamp = timestamp_out.getTime();

    outputQ.push(bu);

    delete bm;
}
