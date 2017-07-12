#include "format_def.h"
#include "arbiter.h"

class Network {
    Arbiter* arbiter[num_pe];
    int msgs_sent[num_pe][num_pe];
    std::queue<Message*> fpga_receive_Q[num_fpga];
    std::queue<Message*> pe_receive_Q[num_pe];
    void transportMessageTo(int i, Message* message);
    void transportOneHop(int current, int dest_pe, Message* message);
public:
    Network();
    ~Network();
    void putMessageAt(int i, Message* message);
    Message* getMessageAt(int i);
    void tick();
    int numMessagesSent;
    int interFPGAtransports;
};
