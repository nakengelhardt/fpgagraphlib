#include "scatterkernel.h"
#include <iostream>

ScatterKernel::ScatterKernel() {
    scatter_hw = new SCATTER_HW;

    scatter_hw->valid_in = 0;
    scatter_hw->barrier_in = 0;
    scatter_hw->message_ack = 1;

    scatter_hw->sys_rst = 1;
    scatter_hw->sys_clk = 0;
    scatter_hw->eval();
    scatter_hw->sys_clk = 1;
    scatter_hw->eval();

    scatter_hw->sys_rst = 0;
}

ScatterKernel::~ScatterKernel() {
    delete scatter_hw;
}

void ScatterKernel::queue(Update* update, edge_t edge, vertexid_t num_neighbors, bool last){
    ScatterKernelInput input;
    input.update = update;
    input.edge = edge;
    input.num_neighbors = num_neighbors;
    input.last = last;
    inputQ.push(input);
}

Message* ScatterKernel::tick() {
    scatter_hw->message_ack = 1;
    scatter_hw->valid_in = 0;
    scatter_hw->barrier_in = 0;
    if(!inputQ.empty()){
        ScatterKernelInput input = inputQ.front();
        setInput(input);
    	scatter_hw->sender_in = input.update->sender;
        scatter_hw->round_in = input.update->roundpar;
        scatter_hw->barrier_in = input.update->barrier;
    	scatter_hw->valid_in = !input.update->barrier;
    }

    if (scatter_hw->ready && (scatter_hw->valid_in || scatter_hw->barrier_in)) {
        // valid_in also ensures inputQ not empty, so update pointer is valid
        if(inputQ.front().last) {
            delete inputQ.front().update;
        }
        inputQ.pop();
    }

    scatter_hw->sys_clk = 0;
    scatter_hw->eval();
    scatter_hw->sys_clk = 1;
    scatter_hw->eval();

    if(scatter_hw->valid_out || scatter_hw->barrier_out){
        Message* message = new Message();
        getOutput(message);
        message->dest_id = scatter_hw->neighbor_out;
        message->dest_pe = message->dest_id >> PEID_SHIFT;
        message->sender = scatter_hw->sender_out;
        message->roundpar = scatter_hw->round_out;
        message->barrier = scatter_hw->barrier_out;
        return message;
    }

    return NULL;
}
