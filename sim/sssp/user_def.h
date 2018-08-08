#pragma once

#include <inttypes.h>

typedef int64_t vertexid_t;

struct edge_t {
    vertexid_t dest_id;
    int dist;
};

struct VertexData {
    int dist;
    vertexid_t parent;
    bool active;
};

struct MessagePayload {
    int dist;
};

struct UpdatePayload {
    int dist;
};

const bool has_edgedata = true;
