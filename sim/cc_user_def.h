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

const bool has_edgedata = false;
