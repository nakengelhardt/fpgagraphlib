#include "pe.h"
#include "graph.h"
#include "network.h"
#include "applykernel.h"
#include "scatterkernel.h"
#include "init.h"

#include <iostream>
#include <stdexcept>
#include <string>

int main(int argc, char **argv, char **env) {
    char const * gname = "../../data/4x4";
    int sz = 64;

    if (argc > 2) {
        gname = argv[1];
        sz = std::stoi(argv[2]);
    }

    // Graph* graph = new Graph("../../data/s11e16", 32768);
    // Graph* graph = new Graph("../../data/s13e16", 131072);
    // Graph* graph = new Graph("../../data/s14e16", 262144);
    Graph* graph = new Graph(gname, sz);

    graph->partition = new GraphPartition(graph->nv);

    std::cout << "Graph has " << graph->nv << " vertices and " << graph->ne << " edges." << std::endl;

    vertexid_t max_vertices_per_pe = 0;
    for(int i = 0; i < graph->nv; i++){
        vertexid_t vname = graph->partition->placement(i);
        vertexid_t local_id = graph->partition->local_id(vname);
        if(local_id > max_vertices_per_pe){
            max_vertices_per_pe = local_id;
        }
        if(graph->nv < 30){
            std::cout << "Vertex " << vname << " has " << graph->num_neighbors(i) << " neighbors: ";
            for(int j = 0; j < graph->num_neighbors(i); j++){
                std::cout << graph->partition->placement(graph->get_neighbor(i,j).dest_id) << " ";
            }
            std::cout << "\n";
        }
    }
    graph->print_dot("last_graph.dot");

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
            message = pe[i]->getSentMessage(supersteps % num_channels);
            if(message){
                if(message->barrier){
                    #ifdef SIM_DEBUG
                    std::cout << message->roundpar << ": Barrier from PE " << i << " for PE " << message->dest_pe << std::endl;
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
                        std::cout << "Superstep " << supersteps << ":";
                        int min_updates = pe[0]->last_completed_superstep_updates;
                        int max_updates = pe[0]->last_completed_superstep_updates;
                        int total_updates = pe[0]->last_completed_superstep_updates;
                        std::cout << " " << pe[0]->last_completed_superstep_updates;
                        for (int j = 1; j < num_pe; j++) {
                            int j_updates = pe[j]->last_completed_superstep_updates;
                            min_updates = std::min(min_updates, j_updates);
                            max_updates = std::max(max_updates, j_updates);
                            total_updates += j_updates;
                            std::cout << " " << j_updates;
                        }
                        std::cout << " updates (imbalance " << (total_updates==0 ? 0 : 100*(max_updates - min_updates)/total_updates) << "%) and";

                        int min_messages = pe[0]->last_completed_superstep_messages;
                        int max_messages = pe[0]->last_completed_superstep_messages;
                        int total_messages = pe[0]->last_completed_superstep_messages;
                        std::cout << " " << pe[0]->last_completed_superstep_messages;
                        for (int j = 1; j < num_pe; j++) {
                            int j_messages = pe[j]->last_completed_superstep_messages;
                            min_messages = std::min(min_messages, j_messages);
                            max_messages = std::max(max_messages, j_messages);
                            total_messages += j_messages;
                            std::cout << " " << j_messages;
                        }
                        std::cout << " messages (imbalance " << (total_messages==0 ? 0 : 100*(max_messages - min_messages)/total_messages) << "%)\n";

                        if(num_messages == 0){
                            inactive = true;
                        }
                        num_messages = 0;
                        for (int j = 0; j < num_pe; j++) {
                            barrier[j] = 0;
                        }
                    }
                } else {
                    #ifdef SIM_DEBUG
                    std::cout << message->roundpar << ": Message from node " << message->sender << " for node " << message->dest_id << std::endl;
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
        delete pe[i];
    }
    std::cout << total_time << std::endl;

    printFinalResult();

    exit(0);
}
