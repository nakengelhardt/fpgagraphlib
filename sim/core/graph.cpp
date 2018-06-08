/* CSR graph storage adapted from graph500 benchmark; portions of this code are Copyright 2010-2011,  Georgia Institute of Technology, USA. See https://github.com/graph500/graph500 */
#include "graph.h"

#include <cstdlib>
#include <stdexcept>
#include <iostream>
#include <fcntl.h>
#include <unistd.h>

Graph::Graph(const char* dumpname, int64_t nedge) {
    packed_edge* IJ = new packed_edge[nedge];

    int fd;
    ssize_t sz;
    if ((fd = open (dumpname, O_RDONLY)) < 0) {
        throw std::runtime_error("Cannot open input graph file");
    }
    sz = nedge * sizeof (*IJ);
    if (sz != read (fd, IJ, sz)) {
        throw std::runtime_error("Error reading input graph file");
    }
    close (fd);

    // for(int i = 0; i < nedge; i++){
    //     std::cout << IJ[i].v0 << " -- " << IJ[i].v1 << std::endl;
    // }

    find_nv(IJ, nedge);
    xoff = new vertexid_t[2*nv+2];
    setup_deg_off (IJ, nedge);
    gather_edges (IJ, nedge);
    if (has_edgedata){
        populate_edgedata();
    }

    delete[] IJ;
}

Graph::~Graph(){
    delete xoff;
    delete xadj;
}

void Graph::find_nv (const packed_edge* IJ, const int64_t nedge) {
    int64_t k;

    maxvtx = -1;
    for (k = 0; k < nedge; ++k) {
        if (IJ[k].v0 > maxvtx) {
            maxvtx = IJ[k].v0;
        }
        if (IJ[k].v1 > maxvtx) {
            maxvtx = IJ[k].v1;
        }
    }
    nv = 1+maxvtx;
}



void Graph::setup_deg_off (const packed_edge* IJ, int64_t nedge) {
    vertexid_t k, accum;
    for (k = 0; k < 2*nv+2; ++k){
        xoff[k] = 0;
    }
    for (k = 0; k < nedge; ++k) {
        vertexid_t i = IJ[k].v0;
        vertexid_t j = IJ[k].v1;
        if (i != j) { /* Skip self-edges. */
            if (i >= 0) ++XOFF(i);
            if (j >= 0) ++XOFF(j);
        }
    }
    accum = 0;
    for (k = 0; k < nv; ++k) {
        vertexid_t tmp = XOFF(k);
        if (tmp < 2) tmp = 2;
        XOFF(k) = accum;
        accum += tmp;
    }
    XOFF(nv) = accum;
    for (k = 0; k < nv; ++k) {
        XENDOFF(k) = XOFF(k);
    }
    xadj = new edge_t[accum];
    for (k = 0; k < accum; ++k) {
        xadj[k].dest_id = -1;
    }
}

void Graph::scatter_edge (const vertexid_t i, const vertexid_t j) {
    int64_t where;
    where = XENDOFF(i)++;
    xadj[where].dest_id = j;
}

static int edge_cmp (const void *a, const void *b)
{
    const vertexid_t ia = ((const edge_t*)a)->dest_id;
    const vertexid_t ib = ((const edge_t*)b)->dest_id;
    if (ia < ib) return -1;
    if (ia > ib) return 1;
    return 0;
}

void Graph::pack_vtx_edges (const vertexid_t i)
{
    int64_t kcur, k;
    if (XOFF(i)+1 >= XENDOFF(i)) return;
    qsort (&xadj[XOFF(i)], XENDOFF(i)-XOFF(i), sizeof(*xadj), edge_cmp);
    kcur = XOFF(i);
    for (k = XOFF(i)+1; k < XENDOFF(i); ++k) {
        if (xadj[k].dest_id != xadj[kcur].dest_id) {
            xadj[++kcur] = xadj[k];
        }
    }
    ++kcur;
    for (k = kcur; k < XENDOFF(i); ++k)
        xadj[k].dest_id = -1;
    XENDOFF(i) = kcur;
}

void Graph::gather_edges (const packed_edge * IJ, int64_t nedge) {
    int64_t k;
    for (k = 0; k < nedge; ++k) {
        vertexid_t i = IJ[k].v0;
        vertexid_t j = IJ[k].v1;
        if (i >= 0 && j >= 0 && i != j) {
            scatter_edge (i, j);
            scatter_edge (j, i);
        }
    }

    ne = 0;
    int64_t v;
    for (v = 0; v < nv; ++v) {
        pack_vtx_edges (v);
        ne += num_neighbors(v);
    }
}

vertexid_t Graph::num_neighbors(vertexid_t vertex){
    return XENDOFF(vertex)-XOFF(vertex);
}

edge_t Graph::get_neighbor(vertexid_t vertex, vertexid_t index){
    if((XOFF(vertex) + index < XOFF(vertex)) || (XOFF(vertex) + index > XENDOFF(vertex))){
        throw std::runtime_error("edge index out of bounds");
    }
    return xadj[XOFF(vertex) + index];
}
