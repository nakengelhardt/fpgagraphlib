#pragma once

#include "pe.h"
#include "graph.h"
#include "format_def.h"

void initVertexData(VertexEntry* init_data, vertexid_t vertex, Graph* graph);
void sendInitMessages(Graph* graph, PE** pe, int* sent);
void printFinalResult();
