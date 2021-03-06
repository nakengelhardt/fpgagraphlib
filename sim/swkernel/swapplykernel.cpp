#include "swapplykernel.h"

#include <iostream>

SWApplyKernel::SWApplyKernel(int pe_id, vertexid_t num_vertices, Graph* graph) : BaseApplyKernel(pe_id, num_vertices, graph){
    level = 0;
}

SWApplyKernel::~SWApplyKernel() {
}

void SWApplyKernel::tick() {
    if(!inputQ.empty()) {
        ApplyKernelInput input = inputQ.front();

        gather(input.message, input.vertex, input.level);

        if (input.level != level) {
            std::cout << "Message for level " << input.level << " received in level " << level << "!\n";
        }

        delete input.message;
        inputQ.pop();
    }
}

void SWApplyKernel::barrier(Message* bm) {
    while (!inputQ.empty()) {
        tick();
    }
#ifdef SIM_DEBUG
    printState();
#endif
    Update* update = NULL;

    int i = 0;
    while (i < num_vertices) {
        VertexEntry* vertex = getLocalVertexEntry(i);
        update = apply(vertex, level);

        if (update) {
            update->sender = vertex->id;
            update->roundpar = (bm->roundpar + 1) % num_channels;
            update->barrier = false;
            outputQ.push(update);
        }

        i++;
    }

    level++;

    Update* bu = new Update();
    bu->sender = pe_id << PEID_SHIFT;
    bu->roundpar = (bm->roundpar + 1) % num_channels;
    bu->barrier = true;

    outputQ.push(bu);

    delete bm;
}
