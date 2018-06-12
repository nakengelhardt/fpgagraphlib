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
};

struct MessagePayload {
    vertexid_t origin;
    vertexid_t via_1;
    vertexid_t via_2;
    int hops;
};

typedef MessagePayload UpdatePayload;
// struct UpdatePayload {
//     vertexid_t origin;
//     vertexid_t via_1;
//     vertexid_t via_2;
// };

const bool has_edgedata = true;
