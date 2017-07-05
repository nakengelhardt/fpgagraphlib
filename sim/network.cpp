#include "network.h"

#include <iostream>

Network::Network() {
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

void Network::transportMessageTo(int pe, Message* message) {
    arbiter[pe]->putMessage(message);
}

void Network::putMessageAt(int i, Message* message) {
    if(message->barrier){
        std::cout << "Distributing barrier from PE " << i << std::endl;
        for(int j = 0; j < num_pe; j++){
            Message* bm = new Message();
            bm->roundpar = message->roundpar;
            bm->barrier = true;
            bm->dest_id = msgs_sent[i][j];
            bm->sender = i << PEID_SHIFT;
            transportMessageTo(j, bm);
            msgs_sent[i][j] = 0;
        }
        delete message;
    } else {
        int dest_pe = message->dest_id >> PEID_SHIFT;
        msgs_sent[i][dest_pe]++;
        transportMessageTo(dest_pe, message);
    }
}

Message* Network::getMessageAt(int i) {
    return arbiter[i]->getMessage();
}
