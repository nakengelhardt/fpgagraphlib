#pragma once

#include <inttypes.h>

typedef int64_t vertexid_t;

struct edge_t {
    vertexid_t dest_id;
};

struct VertexData {
    vertexid_t parent;
};

struct MessagePayload {
};

struct UpdatePayload {
};

const bool has_edgedata = false;
