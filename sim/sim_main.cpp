#include "pe.h"
#include "graph.h"
#include "network.h"

#include "verilated.h"

#include <iostream>
#include <stdexcept>



int main(int argc, char **argv, char **env) {
    // Verilated::commandArgs(argc, argv);

    Graph* graph = new Graph("../data/4x4", 64);

    graph->partition = new GraphPartition();

    std::cout << "Graph has " << graph->nv << " vertices and " << graph->ne << " edges." << std::endl;

    vertexid_t max_vertices_per_pe = 0;
    for(int i = 0; i < graph->nv; i++){
        vertexid_t vname = graph->partition->placement(i);
        vertexid_t local_id = graph->partition->local_id(vname);
        if(local_id > max_vertices_per_pe){
            max_vertices_per_pe = local_id;
        }
        std::cout << "Vertex " << vname << " has " << graph->num_neighbors(i) << " neighbors: ";
        for(int j = 0; j < graph->num_neighbors(i); j++){
            std::cout << graph->partition->placement(graph->get_neighbor(i,j).dest_id) << " ";
        }
        std::cout << std::endl;
    }

    // add 1 for bound
    max_vertices_per_pe++;
    std::cout << "Max vertices per PE: " << max_vertices_per_pe << std::endl;

    VertexData* init_data = new VertexData[num_pe*max_vertices_per_pe];

    for(int i = 0; i < num_pe*max_vertices_per_pe; i++){
        init_data[i].id = 0;
        init_data[i].in_use = false;
        init_data[i].active = false;
    }

    for(int i = 0; i < graph->nv; i++){
        vertexid_t ii = graph->partition->placement(i);
        vertexid_t local_id = graph->partition->local_id(ii);
        int pe_id = graph->partition->pe_id(ii);
        init_data[pe_id*max_vertices_per_pe+local_id].id = ii;
        init_data[pe_id*max_vertices_per_pe+local_id].nneighbors = graph->num_neighbors(i);
        init_data[pe_id*max_vertices_per_pe+local_id].nrecvd = 0;
        init_data[pe_id*max_vertices_per_pe+local_id].sum = 0.0;
    }


    PE** pe = new PE*[num_pe];

    for (int p = 0; p < num_pe; p++) {
        Apply* apply = new Apply(&init_data[p*max_vertices_per_pe], max_vertices_per_pe);
        Scatter* scatter = new Scatter(graph);
        pe[p] = new PE(apply, scatter);
    }

    Network* network = new Network();

    int sent[num_pe];
    for (int i = 0; i < num_pe; i++){
        sent[i] = 0;
    }
    Message* message;
    for(int i = 0; i < graph->nv; i++){
        message = new Message();
        message->sender = 0;
        message->dest_id = graph->partition->placement(i);
        int pe_id = graph->partition->pe_id(graph->partition->placement(i));
        message->dest_pe = pe_id;
        message->dest_fpga = 0;
        message->roundpar = 3;
        message->barrier = false;
        message->payload.weight = 0.15/graph->nv;
        pe[pe_id]->putMessageToReceive(message);
        sent[pe_id]++;
    }
    for(int i = 0; i < num_pe; i++){
        message = new Message();
        message->sender = i;
        message->dest_id = sent[i];
        message->dest_pe = i;
        message->roundpar = 3;
        message->barrier = true;
        pe[i]->putMessageToReceive(message);
    }

    int num_messages = 0;
    int cycles = 0;
    int supersteps = 0;
    int barrier[num_pe];
    for (int i = 0; i < num_pe; i++) {
        barrier[i] = 0;
    }
    while (supersteps < 31){
        for(int i = 0; i < num_pe; i++){
            pe[i]->tick();
            message = pe[i]->getSentMessage();
            if(message){
                if(message->barrier){
                    barrier[i]++;
                    int all_barriers = 1;
                    for (int j = 0; j < num_pe; j++) {
                        if(!barrier[j]){
                            all_barriers = 0;
                            break;
                        }
                    }
                    if(all_barriers){
                        supersteps++;
                        std::cout << "Superstep " << supersteps << ": " << num_messages << " messages (not counting barriers)" << std::endl;
                        num_messages = 0;
                        for (int j = 0; j < num_pe; j++) {
                            barrier[j] = 0;
                        }
                    }
                } else {
                    num_messages++;
                }
                network->putMessageAt(i, message);
            }
            message = network->getMessageAt(i);
            if(message){
                pe[i]->putMessageToReceive(message);
            }
        }
        cycles++;
    }

    std::cout << "Messages transported between FPGAs: " << network->interFPGAtransports
    << " out of " << network->numMessagesSent << std::endl;

    exit(0);
}
