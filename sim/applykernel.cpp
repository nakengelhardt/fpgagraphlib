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

void ApplyKernel::do_reset(){
    top->valid_in = 0;
    top->barrier_in = 0;
    top->sys_rst = 1;
    top->sys_clk = 0;
    top->eval();
    top->sys_clk = 1;
    top->eval();

    top->sys_rst = 0;
}

ApplyKernel::ApplyKernel(int n) {
    num_vertices = n;
    vertex_data = new VertexData[num_vertices];
    top = new Vpr_apply;
    do_reset();
}

ApplyKernel::ApplyKernel(VertexData* init_data, int n) {
    num_vertices = n;
    vertex_data = init_data;
    top = new Vpr_apply;
    do_reset();
}

ApplyKernel::~ApplyKernel() {
    delete top;
}

void ApplyKernel::queueInput(Message* message, VertexData* vertex, int level) {
    ApplyKernelInput input;
    input.message = message;
    input.vertex = vertex;
    input.level = level;
    inputQ.push(input);
}

Update* ApplyKernel::tick() {
    Update* update = NULL;

    top->update_ack = 1;
    top->valid_in = 0;
    top->barrier_in = 0;

    if(!inputQ.empty()) {
        ApplyKernelInput input = inputQ.front();
        Message* message = input.message;
        VertexData* vertex = input.vertex;
        top->level_in = input.level;
        bool busy_stall = false;
        if (vertex) {
            top->state_in_nneighbors = vertex->nneighbors;
            top->state_in_nrecvd = vertex->nrecvd;
            *((float*) &top->state_in_sum) = vertex->sum;
            busy_stall = vertex->in_use;
        } else {
            top->state_in_nneighbors = 0;
            top->state_in_nrecvd = 0;
            *((float*) &top->state_in_sum) = 0;
        }
        if (message && !busy_stall) {
            top->nodeid_in = message->dest_id;
            top->sender_in = message->sender;
            *((float*) &top->message_in_weight) = message->payload.weight;
            top->barrier_in = message->barrier;
            top->valid_in = !message->barrier;
        }
        if (busy_stall) {
            // std::cout << "stalling on vertex " << message->dest_id << std::endl;
        }
    }

    if (top->ready && (top->valid_in || top->barrier_in)) {
        if(inputQ.front().vertex){
            inputQ.front().vertex->in_use = true;
            // std::cout << "Checkout vertex " << top->nodeid_in
            // << ": nneighbors=" << top->state_in_nneighbors
            // << ", nrecvd=" << top->state_in_nrecvd
            // << ", sum=" << *((float*) &top->state_out_sum)
            // << ", message add " << *((float*) &top->message_in_weight)
            // << std::endl;
        }
        // valid_in also ensures inputQ not empty, so message pointer is valid
        // it might be NULL but delete null is ok and does nothing
        delete inputQ.front().message;
        inputQ.pop();
    }

    top->sys_clk = 0;
    top->eval();
    top->sys_clk = 1;
    top->eval();

    if(top->state_barrier) {
        printState();
    }

    if (top->state_valid) {
        VertexData* vertex = getDataRef(top->nodeid_out);
        // std::cout << "Writeback vertex " << top->nodeid_out
        // << ": " << "nneighbors " << vertex->nneighbors << " -> " << top->state_out_nneighbors
        // << ", nrecvd " << vertex->nrecvd << " -> " << top->state_out_nrecvd
        // << ", sum " << vertex->sum << " -> " << *((float*) &top->state_out_sum)
        // << ", in use: " << (vertex->in_use ? "yes" : "***NO***")
        // << std::endl;

        vertex->nneighbors = top->state_out_nneighbors;
        vertex->nrecvd = top->state_out_nrecvd;
        vertex->sum = *((float*) &top->state_out_sum);
        vertex->in_use = false;
    }

    if (top->update_valid || top->barrier_out) {
        update = new Update;
        update->sender = top->update_sender;
        update->roundpar = top->update_round;
        update->barrier = top->barrier_out;
        update->payload.weight = *((float*) &top->update_out_weight);

        if (!top->barrier_out){
            std::cout << "Update vertex " << update->sender
            << ", weight=" << update->payload.weight
            << std::endl;
        }
    }


    return update;
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
