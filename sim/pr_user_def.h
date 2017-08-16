#pragma once

#include "pr_applykernel.h"
#include "pr_scatterkernel.h"
#include <inttypes.h>

typedef int64_t vertexid_t;

struct edge_t {
    vertexid_t dest_id;
};

struct VertexData {
    int id;
    vertexid_t nneighbors;
    vertexid_t nrecvd;
    float sum;
    bool in_use;
    bool active;
};

struct MessagePayload {
    float weight;
};

struct UpdatePayload {
    float weight;
};

const int num_channels = 4;
const int NODEID_MASK = 0xFFFF;
const int PEID_SHIFT = 16;
const int num_pe = 4;
const int num_fpga = 2;

const bool has_edgedata = false;
