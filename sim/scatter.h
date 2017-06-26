#include "scatterkernel.h"
#include "graph.h"

class Scatter {
    ScatterKernel* scatterkernel;
    Graph* graph;
public:
    Scatter(Graph* graph);
    ~Scatter();
    std::queue<Update*> updateQ;
    Message* receiveUpdate(Update* update);
};
