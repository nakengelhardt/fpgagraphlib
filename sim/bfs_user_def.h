#pragma once

#include "bfs_applykernel.h"
#include "bfs_scatterkernel.h"
#include <inttypes.h>

typedef int64_t vertexid_t;

struct edge_t {
    vertexid_t dest_id;
};

struct VertexData {
    int id;
    vertexid_t parent;
    bool in_use;
    bool active;
};

struct MessagePayload {
};

struct UpdatePayload {
};

const bool has_edgedata = false;
