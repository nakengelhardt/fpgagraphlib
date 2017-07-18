#include "applykernel.h"

#include <stdexcept>
#include <iostream>

VertexData* ApplyKernel::getDataRef(vertexid_t vertex){
    if (vertex == 0){
        std::cout << "***Accessing Vertex 0***" << std::endl;
    }
    int local_id = vertex & NODEID_MASK;
    return &vertex_data[local_id];
}

ApplyKernel::ApplyKernel(int n) {
    num_vertices = n;
    vertex_data = new VertexData[num_vertices];
    memset(vertex_data, 0, num_vertices*sizeof(VertexData));

    do_init();
}

ApplyKernel::ApplyKernel(VertexData* init_data, int n) {
    num_vertices = n;
    vertex_data = init_data;

    do_init();
}

ApplyKernel::~ApplyKernel() {
    delete gather_hw;
    delete apply_hw;
}

void ApplyKernel::do_init(){
    gather_hw = new Vpr_gather;
    apply_hw = new Vpr_apply;
    num_in_use_gather = 0;
    num_in_use_apply = 0;

    gather_hw->valid_in = 0;
    gather_hw->state_ack = 1;
    gather_hw->sys_rst = 1;
    gather_hw->sys_clk = 0;
    gather_hw->eval();
    gather_hw->sys_clk = 1;
    gather_hw->eval();
    gather_hw->sys_rst = 0;

    apply_hw->valid_in = 0;
    apply_hw->barrier_in = 0;
    apply_hw->update_ack = 1;
    apply_hw->sys_rst = 1;
    apply_hw->sys_clk = 0;
    apply_hw->eval();
    apply_hw->sys_clk = 1;
    apply_hw->eval();
    apply_hw->sys_rst = 0;
}

void ApplyKernel::queueInput(Message* message, VertexData* vertex, int level) {
    ApplyKernelInput input;
    input.message = message;
    input.vertex = vertex;
    input.level = level;
    inputQ.push(input);
    gather_tick();
}

Update* ApplyKernel::getUpdate(){
    gather_tick();
    apply_tick();
    Update* update = NULL;
    if(!outputQ.empty()){
        update = outputQ.front();
        outputQ.pop();
    }
    return update;
}

void ApplyKernel::apply_tick() {
    apply_hw->update_ack = 1;

    apply_hw->sys_clk = 0;
    apply_hw->eval();
    apply_hw->sys_clk = 1;
    apply_hw->eval();

    if (apply_hw->state_valid) {
        VertexData* vertex = getDataRef(apply_hw->nodeid_out);
        if(apply_hw->state_out_nneighbors != vertex->nneighbors
          || apply_hw->state_out_nrecvd != 0
          || apply_hw->state_out_sum != 0
          || apply_hw->state_out_active != 0) {
            std::cout << "Apply not resetting state properly:" << std::endl;
            std::cout << "apply_hw->state_out_nneighbors = " << apply_hw->state_out_nneighbors
            << " (" << vertex->nneighbors << ")"
            << ", apply_hw->state_out_nrecvd = " << apply_hw->state_out_nrecvd
            << ", apply_hw->state_out_sum = " << apply_hw->state_out_sum
            << ", apply_hw->state_out_active = " << apply_hw->state_out_active
            << std::endl;

        }
        vertex->sum = 0;
        vertex->nrecvd = 0;
        vertex->active = 0;
        num_in_use_apply--;
    }

    if ((apply_hw->update_valid || apply_hw->barrier_out) && apply_hw->update_ack) {
        Update* update = new Update;
        update->sender = apply_hw->update_sender;
        update->roundpar = apply_hw->update_round;
        update->barrier = apply_hw->barrier_out;
        update->payload.weight = *((float*) &apply_hw->update_out_weight);
        outputQ.push(update);
    }

}

void ApplyKernel::barrier(Message* bm) {
    // std::cout << "Barrier received, emptying queue" << std::endl;
    while (!inputQ.empty() || num_in_use_gather > 0) {
        gather_tick();
    }

    int i = 0;
    while (i < num_vertices) {
        VertexData* vertex = &vertex_data[i];
        if (vertex->active){
            if(vertex->in_use) {
                std::cout << "Vertex " << vertex->id << " still marked in use." << std::endl;
            }
            if(vertex->nrecvd != vertex->nneighbors) {
                std::cout << "Vertex " << vertex->id << " has not received all messages." << std::endl;
            }

            apply_hw->nodeid_in = vertex->id;
            apply_hw->state_in_nneighbors = vertex->nneighbors;
            apply_hw->state_in_nrecvd = vertex->nrecvd;
            *((float*) &apply_hw->state_in_sum) = vertex->sum;
            apply_hw->state_in_active = vertex->active;
            apply_hw->round_in = (bm->roundpar + 1) % num_channels;
            apply_hw->valid_in = 1;
            apply_hw->barrier_in = 0;

            if (apply_hw->ready && apply_hw->valid_in) {
                i++;
                num_in_use_apply++;
                // std::cout << "Apply in vertex "<< vertex->id << std::endl;
            }

            apply_tick();
        } else {
            i++;
        }
    }

    apply_hw->nodeid_in = 0;
    apply_hw->state_in_nneighbors = 0;
    apply_hw->state_in_nrecvd = 0;
    apply_hw->state_in_sum = 0;
    apply_hw->state_in_active = 0;
    apply_hw->round_in = (bm->roundpar + 1) % num_channels;
    apply_hw->valid_in = 0;
    apply_hw->barrier_in = 1;

    bool accepted = apply_hw->ready;
    while (true) {
        apply_hw->sys_clk = 0;
        apply_hw->eval();
        apply_hw->sys_clk = 1;
        apply_hw->eval();
        if(accepted) break;
        accepted = apply_hw->ready;
    }

    apply_hw->barrier_in = 0;

    while (num_in_use_apply > 0) {
        apply_tick();
    }

    delete bm;
}

void ApplyKernel::gather_tick() {

    gather_hw->valid_in = 0;
    gather_hw->state_ack = 1;

    if(!inputQ.empty()) {
        ApplyKernelInput input = inputQ.front();
        Message* message = input.message;
        VertexData* vertex = input.vertex;
        bool busy_stall = vertex->in_use;

        gather_hw->level_in = input.level;
        gather_hw->state_in_nneighbors = vertex->nneighbors;
        gather_hw->state_in_nrecvd = vertex->nrecvd;
        *((float*) &gather_hw->state_in_sum) = vertex->sum;
        gather_hw->state_in_active = vertex->active;
        gather_hw->nodeid_in = message->dest_id;
        gather_hw->sender_in = message->sender;
        *((float*) &gather_hw->message_in_weight) = message->payload.weight;
        gather_hw->valid_in = !busy_stall;
    }

    if (gather_hw->ready && gather_hw->valid_in) {
        inputQ.front().vertex->in_use = true;
        num_in_use_gather++;
        // std::cout << "Checkout vertex " << gather_hw->nodeid_in
        // << ": nneighbors=" << gather_hw->state_in_nneighbors
        // << ", nrecvd=" << gather_hw->state_in_nrecvd
        // << ", sum=" << *((float*) &gather_hw->state_out_sum)
        // << ", message add " << *((float*) &gather_hw->message_in_weight)
        // << ", now in use: " << num_in_use_gather
        // << std::endl;
        delete inputQ.front().message;
        inputQ.pop();
    }

    gather_hw->sys_clk = 0;
    gather_hw->eval();
    gather_hw->sys_clk = 1;
    gather_hw->eval();

    if (gather_hw->state_valid) {
        VertexData* vertex = getDataRef(gather_hw->nodeid_out);
        if (vertex->in_use) {
            num_in_use_gather--;
            // std::cout << "Writeback vertex " << gather_hw->nodeid_out
            // << ": " << "nneighbors " << vertex->nneighbors << " -> " << gather_hw->state_out_nneighbors
            // << ", nrecvd " << vertex->nrecvd << " -> " << gather_hw->state_out_nrecvd
            // << ", sum " << vertex->sum << " -> " << *((float*) &gather_hw->state_out_sum)
            // << ", remaining in use: " << num_in_use_gather
            // << std::endl;
            vertex->nneighbors = gather_hw->state_out_nneighbors;
            vertex->nrecvd = gather_hw->state_out_nrecvd;
            vertex->sum = *((float*) &gather_hw->state_out_sum);
            vertex->active = gather_hw->state_out_active;
            vertex->in_use = false;
        }
    }

}

void ApplyKernel::printState(){
    for(int i = 0; i < num_vertices; i++){
        std::cout << i ;
        if(vertex_data[i].in_use){
            std::cout << "*";
        } else {
            std::cout << " ";
        }
        std::cout << "{" << vertex_data[i].nrecvd << "/" << vertex_data[i].nneighbors
        << ", " << vertex_data[i].sum << "}" << std::endl;
    }
}
