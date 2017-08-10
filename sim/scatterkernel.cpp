#include "scatterkernel.h"
#include <iostream>

ScatterKernel::ScatterKernel() {
    top = new Vsssp_scatter;

    top->valid_in = 0;
    top->barrier_in = 0;
    top->message_ack = 1;

    top->sys_rst = 1;
    top->sys_clk = 0;
    top->eval();
    top->sys_clk = 1;
    top->eval();

    top->sys_rst = 0;
}

ScatterKernel::~ScatterKernel() {
    delete top;
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
    top->message_ack = 1;
    top->valid_in = 0;
    top->barrier_in = 0;
    if(!inputQ.empty()){
        ScatterKernelInput input = inputQ.front();
        top->update_in_dist = input.update->payload.dist;
        top->num_neighbors_in = input.num_neighbors;
    	top->neighbor_in = input.edge.dest_id;
    	top->sender_in = input.update->sender;
        top->round_in = input.update->roundpar;
        top->barrier_in = input.update->barrier;
    	top->valid_in = !input.update->barrier;
        if(has_edgedata){
            top->edgedata_in_dist = input.edge.dist;
        }
    }

    if (top->ready && (top->valid_in || top->barrier_in)) {
        // valid_in also ensures inputQ not empty, so update pointer is valid
        if(inputQ.front().last) {
            delete inputQ.front().update;
        }
        inputQ.pop();
    }

    top->sys_clk = 0;
    top->eval();
    top->sys_clk = 1;
    top->eval();

    if(top->valid_out || top->barrier_out){
        Message* message = new Message();
        message->payload.dist = top->message_out_dist;
        message->dest_id = top->neighbor_out;
        message->dest_pe = message->dest_id >> PEID_SHIFT;
        message->sender = top->sender_out;
        message->roundpar = top->round_out;
        message->barrier = top->barrier_out;
        return message;
    }

    return NULL;
}
