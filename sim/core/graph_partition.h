#pragma once

#include "format_def.h"

class GraphPartition {
public:
    GraphPartition(int num_vertices);
    vertexid_t placement(vertexid_t vertex);
    vertexid_t origin(vertexid_t vertex);
    vertexid_t origin(int pe_id, vertexid_t local_id);
    int pe_id(vertexid_t vertex);
    vertexid_t local_id(vertexid_t vertex);
};
