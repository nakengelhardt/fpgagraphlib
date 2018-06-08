#include "scatterkernel.h"

void ScatterKernel::setInput(ScatterKernelInput input){
    *((float*) &scatter_hw->update_in_weight)  = input.update->payload.weight;
}

void ScatterKernel::getOutput(Message* message){
    message->payload.weight = *((float*) &scatter_hw->message_out_weight);
}
