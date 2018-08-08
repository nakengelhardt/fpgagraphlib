#include "hwapplykernel.h"

#include <stdexcept>
#include <iostream>

HWApplyKernel::HWApplyKernel(int pe_id, vertexid_t num_vertices, Graph* graph) : BaseApplyKernel(pe_id, num_vertices, graph){
    gather_hw = new Vgather;
    apply_hw = new Vapply;

    do_init();
}

void HWApplyKernel::do_init(){
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
    apply_hw->state_ack = 1;
    apply_hw->sys_rst = 1;
    apply_hw->sys_clk = 0;
    apply_hw->eval();
    apply_hw->sys_clk = 1;
    apply_hw->eval();
    apply_hw->sys_rst = 0;
}

HWApplyKernel::~HWApplyKernel() {
    delete gather_hw;
    delete apply_hw;
}

void HWApplyKernel::apply_tick() {
    apply_hw->update_ack = 1;

    apply_hw->sys_clk = 0;
    apply_hw->eval();
    apply_hw->sys_clk = 1;
    apply_hw->eval();

    if (apply_hw->state_valid) {
        VertexEntry* vertex = getVertexEntry(apply_hw->nodeid_out);
        getStateOutputApply(&(vertex->data));
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

void HWApplyKernel::barrier(Message* bm) {
#ifdef SIM_DEBUG
    std::cout << "Barrier received, emptying queue" << std::endl;
#endif
    while (!inputQ.empty() || num_in_use_gather > 0) {
        gather_tick();
    }
#ifdef SIM_DEBUG
    printState();
#endif

    int i = 0;
    while (i < num_vertices) {
        VertexEntry* vertex = getLocalVertexEntry(i);
        if(vertex->in_use) {
            std::cout << "Vertex " << vertex->id << " still marked in use." << std::endl;
        }

        apply_hw->nodeid_in = vertex->id;
        setStateInputApply(&(vertex->data));
        apply_hw->round_in = (bm->roundpar + 1) % num_channels;
        apply_hw->valid_in = 1;
        apply_hw->state_in_valid = 1;
        apply_hw->barrier_in = 0;

        if (apply_hw->ready && apply_hw->valid_in) {
            i++;
            num_in_use_apply++;
#ifdef SIM_DEBUG
            std::cout << "Apply in vertex "<< vertex->id << std::endl;
#endif
        }

        apply_tick();
    }

    apply_hw->nodeid_in = 0;
    resetStateInputApply();
    apply_hw->round_in = (bm->roundpar + 1) % num_channels;
    apply_hw->valid_in = 1;
    apply_hw->state_in_valid = 0;
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

void HWApplyKernel::gather_tick() {

    gather_hw->valid_in = 0;
    gather_hw->state_ack = 1;

    if(!inputQ.empty()) {
        ApplyKernelInput input = inputQ.front();
        Message* message = input.message;
        VertexEntry* vertex = input.vertex;
        bool busy_stall = vertex->in_use;

        gather_hw->level_in = input.level;
        setStateInputGather(&(vertex->data));
        gather_hw->nodeid_in = message->dest_id;
        gather_hw->sender_in = message->sender;
        setMessageInputGather(message);
        gather_hw->valid_in = !busy_stall;
    }

    if (gather_hw->ready && gather_hw->valid_in) {
        inputQ.front().vertex->in_use = true;
        num_in_use_gather++;
#ifdef SIM_DEBUG
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
        VertexEntry* vertex = getVertexEntry(gather_hw->nodeid_out);
        if (vertex->in_use) {
            num_in_use_gather--;
#ifdef SIM_DEBUG
            vertexWritebackPrint(vertex);
#endif
            getStateOutputGather(&(vertex->data));
            vertex->in_use = false;
        }
    }

}

void HWApplyKernel::tick() {
    gather_tick();
    apply_tick();
}

void HWApplyKernel::vertexCheckoutPrint(){
    std::cout << "Checkout vertex " << static_cast<int>(gather_hw->nodeid_in) << std::endl;
}

void HWApplyKernel::vertexWritebackPrint(VertexEntry* vertex){
    std::cout << "Writeback vertex " << static_cast<int>(gather_hw->nodeid_out) << std::endl;
}
