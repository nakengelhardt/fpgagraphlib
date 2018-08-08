#pragma once

#include <inttypes.h>

typedef int64_t vertexid_t;

struct edge_t {
    vertexid_t dest_id;
};

struct VertexData {
    vertexid_t nneighbors;
    vertexid_t nrecvd;
    float sum;
    bool active;
};

struct MessagePayload {
    float weight;
};

struct UpdatePayload {
    float weight;
};

const bool has_edgedata = false;
