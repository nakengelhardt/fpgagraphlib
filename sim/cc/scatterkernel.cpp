#include "scatterkernel.h"

ScatterKernel::ScatterKernel(int pe_id, vertexid_t num_vertices) : HWScatterKernel(pe_id, num_vertices) {
    scatter_latency = 0;
}

void ScatterKernel::setInput(ScatterKernelInput input){
    scatter_hw->update_in_color = input.update->payload.color;
}

void ScatterKernel::getOutput(Message* message){
    message->payload.color = scatter_hw->message_out_color;
}
