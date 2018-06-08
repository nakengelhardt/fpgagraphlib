#include "pe.h"
#include "graph.h"
#include "network.h"
#include "applykernel.h"
#include "scatterkernel.h"
#include "init.h"

#include <iostream>
#include <stdexcept>


int main(int argc, char **argv, char **env) {
    // Verilated::commandArgs(argc, argv);

    Graph* graph = new Graph("../../data/4x4", 64);
    // Graph* graph = new Graph("../data/s11e16", 32768);
    // Graph* graph = new Graph("../data/s13e16", 131072);
    // Graph* graph = new Graph("../data/s14e16", 262144);

    graph->partition = new GraphPartition(graph->nv);

    std::cout << "Graph has " << graph->nv << " vertices and " << graph->ne << " edges." << std::endl;

    vertexid_t max_vertices_per_pe = 0;
    for(int i = 0; i < graph->nv; i++){
        vertexid_t vname = graph->partition->placement(i);
        vertexid_t local_id = graph->partition->local_id(vname);
        if(local_id > max_vertices_per_pe){
            max_vertices_per_pe = local_id;
        }
        // std::cout << "Vertex " << vname << " has " << graph->num_neighbors(i) << " neighbors: ";
        // for(int j = 0; j < graph->num_neighbors(i); j++){
        //     std::cout << graph->partition->placement(graph->get_neighbor(i,j).dest_id) << " ";
        // }
        // std::cout << std::endl;
    }

    // add 1 for bound
    max_vertices_per_pe++;
    std::cout << "Max vertices per PE: " << max_vertices_per_pe << " (PEID_SHIFT = " << PEID_SHIFT << ")"<< std::endl;


    PE** pe = new PE*[num_pe];

    for (int p = 0; p < num_pe; p++) {
        Apply* apply = new Apply(new ApplyKernel(p, max_vertices_per_pe, graph));
        Scatter* scatter = new Scatter(graph, new ScatterKernel(p, max_vertices_per_pe));
        pe[p] = new PE(apply, scatter);
    }

    Network* network = new Network();

    int sent[num_pe];
    for (int i = 0; i < num_pe; i++){
        sent[i] = 0;
    }
    sendInitMessages(graph, pe, sent);

    Message* message;
    for(int i = 0; i < num_pe; i++){
        message = new Message();
        message->sender = i;
        message->dest_id = sent[i];
        message->dest_pe = i;
        message->roundpar = 3;
        message->barrier = true;
        message->timestamp = 0;
        pe[i]->putMessageToReceive(message);
    }

    int num_messages = 0;
    int cycles = 0;
    int supersteps = 0;
    int barrier[num_pe];
    for (int i = 0; i < num_pe; i++) {
        barrier[i] = 0;
    }
    bool inactive = false;
    while (!inactive){
        for(int i = 0; i < num_pe; i++){
            pe[i]->tick();
            message = pe[i]->getSentMessage();
            if(message){
                if(message->barrier){
                    #ifdef DEBUG_PRINT
                    std::cout << message->timestamp << ": Barrier from PE " << i << " for PE " << message->dest_pe << std::endl;
                    #endif
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
                        if(num_messages == 0){
                            inactive = true;
                        }
                        num_messages = 0;
                        for (int j = 0; j < num_pe; j++) {
                            barrier[j] = 0;
                        }
                    }
                } else {
                    #ifdef DEBUG_PRINT
                    std::cout << message->timestamp << ": Message from node " << message->sender << " for node " << message->dest_id << std::endl;
                    #endif
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

    std::cout << "Simulation cycles: " << cycles << std::endl;

    std::cout << "Messages transported between FPGAs: " << network->interFPGAtransports
    << " out of " << network->numMessagesSent << std::endl;

    std::cout << "Final time: ";
    int total_time = 0;
    for (int i = 0; i < num_pe; i++) {
        int pe_time = pe[i]->getTime();
        if (total_time < pe_time){
            total_time = pe_time;
        }
        // std::cout << "PE " << i << ": " << pe_time << std::endl;
    }
    std::cout << total_time << std::endl;

    exit(0);
}
