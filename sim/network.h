#include "format_def.h"
#include "arbiter.h"

class Network {
    Arbiter* arbiter[num_pe];
    int msgs_sent[num_pe][num_pe];
    void transportMessageTo(int i, Message* message);
public:
    Network();
    ~Network();
    void putMessageAt(int i, Message* message);
    Message* getMessageAt(int i);
};
