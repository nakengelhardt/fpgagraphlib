#pragma once

#include <inttypes.h>

typedef int64_t vertexid_t;

struct edge_t {
    vertexid_t dest_id;
    vertexid_t dest_degree;
};

struct VertexData {
    int send_in_level;
    int num_triangles;
    bool active;
};

struct MessagePayload {
    vertexid_t origin;
    int hops;
};

typedef MessagePayload UpdatePayload;

const bool has_edgedata = true;
