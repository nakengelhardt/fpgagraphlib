#include "graph.h"

void Graph::populate_edgedata(){
    for (int i = 0; i < nv; i++) {
        int n = num_neighbors(i);
        for (int j = 0; j < n; j++) {
            int d = num_neighbors(xadj[XOFF(i) + j].dest_id);
            xadj[XOFF(i) + j].dest_degree = d;
        }
    }
}
