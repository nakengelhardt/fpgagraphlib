#include "scatterkernel.h"

void ScatterKernel::setInput(ScatterKernelInput input){
    scatter_hw->update_in_dist = input.update->payload.dist;
    scatter_hw->edgedata_in_dist = input.edge.dist;
}

void ScatterKernel::getOutput(Message* message){
    message->payload.dist = scatter_hw->message_out_dist;
}
