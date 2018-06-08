#pragma once

#include <inttypes.h>

typedef int64_t vertexid_t;

struct edge_t {
    vertexid_t dest_id;
};

struct VertexData {
    vertexid_t color;
};

struct MessagePayload {
    vertexid_t color;
};

struct UpdatePayload {
    vertexid_t color;
};

const bool has_edgedata = false;
