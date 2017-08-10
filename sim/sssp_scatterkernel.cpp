#include "scatterkernel.h"

#ifdef SSSP

void ScatterKernel::setInput(ScatterKernelInput input){
    scatter_hw->update_in_dist = input.update->payload.dist;
    scatter_hw->num_neighbors_in = input.num_neighbors;
    scatter_hw->neighbor_in = input.edge.dest_id;
    scatter_hw->edgedata_in_dist = input.edge.dist;
}

void ScatterKernel::getOutput(Message* message){
    message->payload.dist = scatter_hw->message_out_dist;
}

#endif
