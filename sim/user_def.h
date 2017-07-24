#ifndef _USER_DEF_H_
#define _USER_DEF_H_
#include <inttypes.h>

typedef int64_t vertexid_t;

struct edge_t {
    vertexid_t dest_id;
    int dist;
};

struct VertexData {
    int id;
    int dist;
    vertexid_t parent;
    bool in_use;
    bool active;
};

struct MessagePayload {
    int dist;
};

struct UpdatePayload {
    int dist;
};

const int num_channels = 4;
const int NODEID_MASK = 0xFF;
const int PEID_SHIFT = 8;
const int num_pe = 4;
const int num_fpga = 2;

const bool has_edgedata = true;

#endif
