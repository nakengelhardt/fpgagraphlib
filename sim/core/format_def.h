#pragma once

#include "user_def.h"
#include "platform_def.h"
#include <cstddef>

struct VertexEntry {
    int id;
    bool in_use;
    bool active;
    VertexData data;
};

struct Message {
    vertexid_t sender;
    vertexid_t dest_id;
    int dest_pe;
    int dest_fpga;
    int roundpar;
    bool barrier;
    int timestamp;
    MessagePayload payload;
};

struct Update {
    vertexid_t sender;
    vertexid_t roundpar;
    bool barrier;
    int timestamp;
    UpdatePayload payload;
};

#define STRINGIFY(x) #x
#define TOSTRING(x) STRINGIFY(x)
#define AT __FILE__ ":" TOSTRING(__LINE__) " : "
