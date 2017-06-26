#ifndef _FORMAT_DEF_H_
#define _FORMAT_DEF_H_

#include "user_def.h"
#include <cstddef>

struct Message {
    vertexid_t sender;
    vertexid_t dest_id;
    int roundpar;
    bool barrier;
    MessagePayload payload;
};

struct Update {
    vertexid_t sender;
    vertexid_t roundpar;
    bool barrier;
    UpdatePayload payload;
};

#endif
