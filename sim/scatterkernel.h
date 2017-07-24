#include "format_def.h"
#include "Vsssp_scatter.h"
#include <queue>

struct ScatterKernelInput{
    Update* update;
    edge_t edge;
    vertexid_t num_neighbors;
    bool last;
};

class ScatterKernel {
    Vsssp_scatter* top;
    std::queue<ScatterKernelInput> inputQ;
public:
    ScatterKernel();
    ~ScatterKernel();
    void queue(Update* update, edge_t edge, vertexid_t num_neighbors, bool last);
    Message* tick();
};
