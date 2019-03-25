#include "relaxedhwapplykernel.h"

#include <stdexcept>
#include <iostream>

RelaxedHWApplyKernel::RelaxedHWApplyKernel(int pe_id, vertexid_t num_vertices, Graph* graph) : BaseApplyKernel(pe_id, num_vertices, graph){
    ga_hw = new Vgatherapply;

    do_init();
}

void RelaxedHWApplyKernel::do_init(){
    num_in_use = 0;

    ga_hw->valid_in = 0;
    ga_hw->state_ack = 1;
    ga_hw->update_ack = 1;
    ga_hw->sys_rst = 1;
    ga_hw->sys_clk = 0;
    ga_hw->eval();
    ga_hw->sys_clk = 1;
    ga_hw->eval();
    ga_hw->sys_rst = 0;
}

RelaxedHWApplyKernel::~RelaxedHWApplyKernel() {
    delete ga_hw;
}

void RelaxedHWApplyKernel::tick() {
    ga_hw->state_ack = 1;
    ga_hw->update_ack = 1;

    if(!inputQ.empty()) {
        ApplyKernelInput input = inputQ.front();
        Message* message = input.message;
        VertexEntry* vertex = input.vertex;
        bool busy_stall = vertex->in_use;

        ga_hw->level_in = input.level;
        setStateInput(&(vertex->data));
        ga_hw->nodeid_in = message->dest_id;
        ga_hw->sender_in = message->sender;
        ga_hw->round_in = (message->roundpar + 1) % num_channels;
        setMessageInput(message);
        ga_hw->valid_in = !busy_stall;
        ga_hw->state_in_valid = 1;
        ga_hw->message_in_valid = 1;
    }

    if (ga_hw->ready && ga_hw->valid_in && ga_hw->message_in_valid) {
        inputQ.front().vertex->in_use = true;
        num_in_use++;
    #ifdef SIM_DEBUG
        std::cout << "Input message from vertex " << ga_hw->sender_in << " for vertex " << ga_hw->nodeid_in << " level=" << ga_hw->level_in << '\n';
        vertexCheckoutPrint();
    #endif
        delete inputQ.front().message;
        inputQ.pop();
    }

    ga_hw->sys_clk = 0;
    ga_hw->eval();
    ga_hw->sys_clk = 1;
    ga_hw->eval();

    if (ga_hw->state_valid) {
        VertexEntry* vertex = getVertexEntry(ga_hw->nodeid_out);
        vertex->in_use = false;
        getStateOutput(&(vertex->data));
        #ifdef SIM_DEBUG
            vertexWritebackPrint();
        #endif
        num_in_use--;
    }

    if (ga_hw->update_valid && ga_hw->update_ack) {
        Update* update = new Update;
        update->sender = ga_hw->update_sender;
        update->roundpar = ga_hw->update_round;
        update->barrier = ga_hw->barrier_out;
        getUpdatePayload(update);
        outputQ.push(update);
#ifdef SIM_DEBUG
        std::cout << "Update: sender=" << update->sender << " barrier=" << update->barrier << " round=" << update->roundpar << '\n';
#endif
    }
    ga_hw->valid_in = 0;
}

void RelaxedHWApplyKernel::barrier(Message* bm) {
#ifdef SIM_DEBUG
    std::cout << ": Barrier received, emptying queue" << std::endl;
#endif
    while (!inputQ.empty() || num_in_use > 0) {
        tick();
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

        ga_hw->nodeid_in = vertex->id;
        setStateInput(&(vertex->data));
        ga_hw->round_in = (bm->roundpar + 1) % num_channels;
        ga_hw->valid_in = 1;
        ga_hw->state_in_valid = 1;
        ga_hw->message_in_valid = 0;
        ga_hw->barrier_in = 0;

#ifdef SIM_DEBUG
        std::cout << "Apply in vertex "<< vertex->id << std::endl;
#endif


        bool accepted = ga_hw->ready;
        while (true) {
            tick();

            if(accepted) break;
            accepted = ga_hw->ready;
        }

        i++;
        num_in_use++;

    }

    ga_hw->nodeid_in = 0;
    resetStateInput();
    ga_hw->round_in = (bm->roundpar + 1) % num_channels;
    ga_hw->valid_in = 1;
    ga_hw->state_in_valid = 0;
    ga_hw->message_in_valid = 0;
    ga_hw->barrier_in = 1;

    bool accepted = ga_hw->ready;
    while (true) {
        tick();

        if(accepted) break;
        accepted = ga_hw->ready;
    }

    ga_hw->valid_in = 0;
    ga_hw->barrier_in = 0;

    while (num_in_use > 0) {
        tick();
    }

    delete bm;
}

void RelaxedHWApplyKernel::vertexCheckoutPrint(){
    std::cout << "Checkout vertex " << static_cast<int>(ga_hw->nodeid_in) << std::endl;
}

void RelaxedHWApplyKernel::vertexWritebackPrint(){
    std::cout << "Writeback vertex " << static_cast<int>(ga_hw->nodeid_out) << std::endl;
}
