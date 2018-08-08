#include "scatterkernel.h"

void ScatterKernel::setInput(ScatterKernelInput input){
    scatter_hw->update_in_color = input.update->payload.color;
}

void ScatterKernel::getOutput(Message* message){
    message->payload.color = scatter_hw->message_out_color;
}
