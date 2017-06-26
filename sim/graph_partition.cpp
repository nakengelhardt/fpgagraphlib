#include "graph_partition.h"

vertexid_t GraphPartition::placement(vertexid_t vertex){
    vertexid_t local_id = (vertex + 1) / num_pe;
    vertexid_t pe_id = (vertex + 1) % num_pe;
    return (pe_id << PEID_SHIFT) + local_id;
}

vertexid_t GraphPartition::origin(vertexid_t vertex){
    vertexid_t l_id = local_id(vertex);
    vertexid_t p_id = pe_id(vertex);
    return (l_id*num_pe+p_id) -1;
}


int GraphPartition::pe_id(vertexid_t vertex){
    return (int) (vertex >> PEID_SHIFT);
}
vertexid_t GraphPartition::local_id(vertexid_t vertex){
    return vertex & NODEID_MASK;
}
