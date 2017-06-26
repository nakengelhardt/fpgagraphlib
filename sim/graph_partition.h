#include "format_def.h"

class GraphPartition {
public:
    vertexid_t placement(vertexid_t vertex);
    vertexid_t origin(vertexid_t vertex);
    int pe_id(vertexid_t vertex);
    vertexid_t local_id(vertexid_t vertex);
};
