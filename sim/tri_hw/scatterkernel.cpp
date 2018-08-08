#include "scatterkernel.h"

void ScatterKernel::setInput(ScatterKernelInput input){
    scatter_hw->update_in_origin = input.update->payload.origin;
    scatter_hw->update_in_hops = input.update->payload.hops;
    scatter_hw->edgedata_in_degree = input.edge.dest_degree;
}

void ScatterKernel::getOutput(Message* message){
    message->payload.origin = scatter_hw->message_out_origin;
    message->payload.hops = scatter_hw->message_out_hops;
}
