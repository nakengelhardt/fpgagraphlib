#include "graph.h"

#ifdef SSSP

#include <random>

std::random_device rd;     // only used once to initialise (seed) engine
std::mt19937 rng(rd());    // random-number engine used (Mersenne-Twister in this case)
std::uniform_int_distribution<int> uni(1,10); // guaranteed unbiased

void Graph::populate_edgedata(){
    for (int i = 0; i < nv; i++) {
        int n = num_neighbors(i);
        for (int j = 0; j < n; j++) {
            xadj[XOFF(i) + j].dist = uni(rng);
        }
    }
}

#endif
