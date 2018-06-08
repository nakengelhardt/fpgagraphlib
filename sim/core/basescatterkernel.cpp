#include "basescatterkernel.h"
#include <iostream>

void BaseScatterKernel::queue(Update* update, edge_t edge, vertexid_t num_neighbors, bool last){
    ScatterKernelInput input;
    input.update = update;
    input.edge = edge;
    input.num_neighbors = num_neighbors;
    input.last = last;
    inputQ.push(input);
}
