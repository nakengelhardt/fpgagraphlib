#include "graph_partition.h"

int NODEID_MASK;
int PEID_SHIFT;

GraphPartition::GraphPartition(int nv){
    int num_vertex_per_pe = nv/num_pe;
    int localidsize = 1;
    while ((1 << localidsize) <= num_vertex_per_pe)
        localidsize++;
    NODEID_MASK = (1 << localidsize) - 1;
    PEID_SHIFT = localidsize;
}

vertexid_t GraphPartition::placement(vertexid_t vertex){
    vertexid_t local_id = (vertex + 1) / num_pe;
    vertexid_t pe_id = (vertex + 1) % num_pe;
    return (pe_id << PEID_SHIFT) + local_id;
}

vertexid_t GraphPartition::origin(vertexid_t vertex){
    vertexid_t local_id = this->local_id(vertex);
    vertexid_t pe_id = this->pe_id(vertex);
    return origin(pe_id, local_id);
}

vertexid_t GraphPartition::origin(int pe_id, vertexid_t local_id){
    return (local_id * num_pe + pe_id) - 1;
}

int GraphPartition::pe_id(vertexid_t vertex){
    return (int) (vertex >> PEID_SHIFT);
}
vertexid_t GraphPartition::local_id(vertexid_t vertex){
    return vertex & NODEID_MASK;
}
