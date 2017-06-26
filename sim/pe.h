#include "apply.h"
#include "scatter.h"

#include <queue>

class PE {
    Apply* apply;
    Scatter* scatter;
    std::queue<Message*> inputQ;
    std::queue<Message*> outputQ;
public:
    PE(Apply* apply, Scatter* scatter);
    void tick();
    Message* getSentMessage();
    void putMessageToReceive(Message* message);
};
