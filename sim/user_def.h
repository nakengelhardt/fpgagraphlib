#ifndef _USER_DEF_H_
#define _USER_DEF_H_
#include <inttypes.h>

typedef int64_t vertexid_t;

struct edge_t {
    vertexid_t dest_id;
};

struct VertexData {
    vertexid_t nneighbors;
    vertexid_t nrecvd;
    float sum;
    bool in_use;
};

struct MessagePayload {
    float weight;
};

struct UpdatePayload {
    float weight;
};

const int num_channels = 4;
const int max_latency = 300;
const int NODEID_MASK = 0xFF;
const int PEID_SHIFT = 8;
const int num_pe = 4;

#endif
