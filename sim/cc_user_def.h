#pragma once

#include "cc_applykernel.h"
#include "cc_scatterkernel.h"
#include <inttypes.h>

typedef int64_t vertexid_t;

struct edge_t {
    vertexid_t dest_id;
};

struct VertexData {
    int id;
    vertexid_t color;
    bool in_use;
    bool active;
};

struct MessagePayload {
    vertexid_t color;
};

struct UpdatePayload {
    vertexid_t color;
};

const int num_channels = 4;
const int NODEID_MASK = 0xFFFF;
const int PEID_SHIFT = 16;
const int num_pe = 4;
const int num_fpga = 2;

const bool has_edgedata = false;
