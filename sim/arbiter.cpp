#include "arbiter.h"

#include <iostream>

Arbiter::Arbiter(int pe_id): pe_id(pe_id) {
    barrier = new int[num_pe];
    num_expected_from_pe = new int[num_pe];
    num_received_from_pe = new int[num_pe];
    current_round = 0;
    for (size_t i = 0; i < num_pe; i++) {
        barrier[i] = 0;
        num_received_from_pe[i] = 0;
    }
}

Arbiter::~Arbiter() {
    delete[] barrier;
    delete[] num_expected_from_pe;
    delete[] num_received_from_pe;
}

void Arbiter::putMessage(Message* m) {
    if(!m){
        return;
    }
    if(m->roundpar != current_round){
        deferredQ.push(m);
        return;
    }
    int src_pe = m->sender >> PEID_SHIFT;
    if(m->barrier){
        barrier[src_pe] = 1;
        num_expected_from_pe[src_pe] = m->dest_id;
        delete m;
        // std::cout << "PE " << pe_id << ": "
        // << "Received barrier from PE " << src_pe
        // << ". Expected messages: " << num_expected_from_pe[src_pe]
        // << ". Received messages: " << num_received_from_pe[src_pe]
        // << std::endl;
    } else {
        // std::cout << "Message " << m->sender << " -> " << m->dest_id << std::endl;
        num_received_from_pe[src_pe]++;
        outputQ.push(m);
    }

    int barrier_done = 1;
    for(int i = 0; i < num_pe; i++){
        if(!barrier[i] || num_expected_from_pe[i] != num_received_from_pe[i]){
            barrier_done = 0;
            break;
        }
    }
    if(!barrier_done){
        return;
    }

    // Barrier - deliver and reset
    Message* bm = new Message();
    bm->sender = pe_id << PEID_SHIFT;
    bm->dest_id = 0;
    bm->roundpar = current_round;
    bm->barrier = true;
    outputQ.push(bm);

    current_round++;
    if(current_round == num_channels){
        current_round = 0;
    }

    for (int i = 0; i < num_pe; i++) {
        barrier[i] = 0;
        num_expected_from_pe[i] = 0;
        num_received_from_pe[i] = 0;
    }

    //handle deferred - should not contain any barriers
    //(next round's can only be generated after the above is delivered)
    Message* first_deferred_again = NULL;
    while(!deferredQ.empty() && deferredQ.front()!=first_deferred_again){
        Message* message = deferredQ.front();
        deferredQ.pop();
        if (message->roundpar != current_round){
            if(!first_deferred_again){
                first_deferred_again = message;
            }
            deferredQ.push(message);
        } else {
            src_pe = message->sender >> PEID_SHIFT;
            num_received_from_pe[src_pe]++;
            outputQ.push(message);
        }
    }
}

Message* Arbiter::getMessage(){
    Message* message = NULL;
    if (!outputQ.empty()) {
        message = outputQ.front();
        outputQ.pop();
    }
    return message;
}
