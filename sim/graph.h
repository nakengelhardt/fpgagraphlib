#ifndef __GRAPH_H__
#define __GRAPH_H__

#include "format_def.h"
#include "graph_partition.h"

struct packed_edge {
    vertexid_t v0;
    vertexid_t v1;
};

class Graph {
    vertexid_t maxvtx, sz;
    vertexid_t * xoff; /* Length 2*nv+2 */
    edge_t * xadj;
    void find_nv(const packed_edge* IJ, const int64_t nedge);
    void setup_deg_off (const packed_edge* IJ, int64_t nedge);
    void scatter_edge (const vertexid_t i, const vertexid_t j);
    void pack_vtx_edges (const vertexid_t i);
    void gather_edges (const packed_edge * IJ, int64_t nedge);
public:
    Graph(const char* dumpname, int64_t nedge);
    ~Graph();
    GraphPartition* partition;
    vertexid_t nv;
    vertexid_t ne;
    vertexid_t num_neighbors(vertexid_t vertex);
    edge_t get_neighbor(vertexid_t vertex, vertexid_t index);
};

#endif
