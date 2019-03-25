#include "network.h"

#include <iostream>

Network::Network() {
    interFPGAtransports = 0;
    numMessagesSent = 0;
    for (int p = 0; p < num_pe; p++) {
        arbiter[p] = new Arbiter(p);
    }

    for (int i = 0; i < num_pe; i++) {
        for (int j = 0; j < num_pe; j++) {
            msgs_sent[i][j] = 0;
        }
    }
}

Network::~Network() {
    for (int i = 0; i < num_pe; i++) {
        delete arbiter[i];
    }
}

void Network::transportOneHop(int current, int dest_pe, Message* message) {
    /*  Topology: fully connected inside FPGA
        place PEs on FPGAs in round-robin (modulo)
    */
    if(current % num_fpga == dest_pe % num_fpga){
        arbiter[dest_pe]->putMessage(message);
    } else {
        fpga_receive_Q[dest_pe % num_fpga].push(message);
        interFPGAtransports++;
    }
}

void Network::tick() {
    for(int i = 0; i < num_pe; i++){
        if(!pe_receive_Q[i].empty()) {
            Message* m = pe_receive_Q[i].front();
            pe_receive_Q[i].pop();
            transportOneHop(i, m->dest_pe, m);
        }
    }
    for (int i = 0; i < num_fpga; i++) {
        // PE endpoint per FPGA = PE with same number as FPGA
        if(!fpga_receive_Q[i].empty()) {
            Message* m = fpga_receive_Q[i].front();
            fpga_receive_Q[i].pop();
            transportOneHop(i, m->dest_pe, m);
        }
    }
}

void Network::putMessageAt(int i, Message* message) {
    numMessagesSent++;
    if(message->barrier){
#ifdef SIM_DEBUG
        std::cout << "Distributing barrier from PE " << i << std::endl;
#endif
        for(int j = 0; j < num_pe; j++){
            Message* bm = new Message();
            bm->roundpar = message->roundpar;
            bm->barrier = true;
            bm->dest_id = msgs_sent[i][j];
            bm->dest_pe = j;
            bm->dest_fpga = 0;
            bm->sender = i << PEID_SHIFT;
            transportOneHop(i, j, bm);
            msgs_sent[i][j] = 0;
        }
        delete message;
    } else {
        int dest_pe = message->dest_id >> PEID_SHIFT;
        msgs_sent[i][dest_pe]++;
        transportOneHop(i, dest_pe, message);
    }
}

Message* Network::getMessageAt(int i) {
    return arbiter[i]->getMessage();
}
