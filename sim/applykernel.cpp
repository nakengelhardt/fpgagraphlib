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
    gather_hw = new GATHER_HW;
    apply_hw = new APPLY_HW;
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
        getStateOutputApply(vertex);
        num_in_use_apply--;
    }

    if ((apply_hw->update_valid || apply_hw->barrier_out) && apply_hw->update_ack) {
        Update* update = new Update;
        update->sender = apply_hw->update_sender;
        update->roundpar = apply_hw->update_round;
        update->barrier = apply_hw->barrier_out;
        getUpdatePayload(update);
        outputQ.push(update);
    }

}

void ApplyKernel::barrier(Message* bm) {
#ifdef DEBUG_PRINT
    std::cout << "Barrier received, emptying queue" << std::endl;
#endif
    while (!inputQ.empty() || num_in_use_gather > 0) {
        gather_tick();
    }
#ifdef DEBUG_PRINT
    printState();
#endif

    int i = 0;
    while (i < num_vertices) {
        VertexData* vertex = &vertex_data[i];
        if (vertex->active){
            if(vertex->in_use) {
                std::cout << "Vertex " << vertex->id << " still marked in use." << std::endl;
            }

            apply_hw->nodeid_in = vertex->id;
            setStateInputApply(vertex);
            apply_hw->round_in = (bm->roundpar + 1) % num_channels;
            apply_hw->valid_in = 1;
            apply_hw->barrier_in = 0;

            if (apply_hw->ready && apply_hw->valid_in) {
                i++;
                num_in_use_apply++;
#ifdef DEBUG_PRINT
                std::cout << "Apply in vertex "<< vertex->id << std::endl;
#endif
            }

            apply_tick();
        } else {
            i++;
        }
    }

    apply_hw->nodeid_in = 0;
    resetStateInputApply();
    apply_hw->round_in = (bm->roundpar + 1) % num_channels;
    apply_hw->valid_in = 0;
    apply_hw->barrier_in = 1;

    bool accepted = apply_hw->ready;
    while (true) {
        apply_tick();

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
        setStateInputGather(vertex);
        gather_hw->nodeid_in = message->dest_id;
        gather_hw->sender_in = message->sender;
        setMessageInputGather(message);
        gather_hw->valid_in = !busy_stall;
    }

    if (gather_hw->ready && gather_hw->valid_in) {
        inputQ.front().vertex->in_use = true;
        num_in_use_gather++;
#ifdef DEBUG_PRINT
        vertexCheckoutPrint();
#endif
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
#ifdef DEBUG_PRINT
            vertexWritebackPrint(vertex);
#endif
            getStateOutputGather(vertex);
            vertex->in_use = false;
        }
    }

}
