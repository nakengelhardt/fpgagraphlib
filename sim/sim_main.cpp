#include "pe.h"
#include "graph.h"
#include "arbiter.h"

#include "verilated.h"

#include <iostream>
#include <stdexcept>
#define STRINGIFY(x) #x
#define TOSTRING(x) STRINGIFY(x)
#define AT __FILE__ ":" TOSTRING(__LINE__) " : "


int main(int argc, char **argv, char **env) {
    // Verilated::commandArgs(argc, argv);

    Graph* graph = new Graph("../../data/4x4", 64);

    graph->partition = new GraphPartition();

    std::cout << "Graph has " << graph->nv << " vertices." << std::endl;

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

    for(int i = 0; i < graph->nv; i++){
        vertexid_t ii = graph->partition->placement(i);
        vertexid_t local_id = graph->partition->local_id(ii);
        int pe_id = graph->partition->pe_id(ii);
        init_data[pe_id*max_vertices_per_pe+local_id].nneighbors = graph->num_neighbors(i);
        init_data[pe_id*max_vertices_per_pe+local_id].nrecvd = 0;
        init_data[pe_id*max_vertices_per_pe+local_id].sum = 0.0;
        init_data[pe_id*max_vertices_per_pe+local_id].in_use = false;
    }

    PE** pe = new PE*[num_pe];
    Arbiter** arbiter = new Arbiter*[num_pe];

    for (int p = 0; p < num_pe; p++) {
        Apply* apply = new Apply(&init_data[p*max_vertices_per_pe], max_vertices_per_pe);
        Scatter* scatter = new Scatter(graph);
        pe[p] = new PE(apply, scatter);
        arbiter[p] = new Arbiter(p);
    }


    int sent[num_pe];
    for (int i = 0; i < num_pe; i++){
        sent[i] = 0;
    }
    Message* message;
    for(int i = 0; i < graph->nv; i++){
        message = new Message();
        message->sender = 0;
        message->dest_id = graph->partition->placement(i);
        message->roundpar = 3;
        message->barrier = false;
        message->payload.weight = 0.15/graph->nv;
        int pe_id = graph->partition->pe_id(graph->partition->placement(i));
        pe[pe_id]->putMessageToReceive(message);
        sent[pe_id]++;
    }
    for(int i = 0; i < num_pe; i++){
        message = new Message();
        message->sender = i;
        message->dest_id = sent[i];
        message->roundpar = 3;
        message->barrier = true;
        pe[i]->putMessageToReceive(message);
    }

    int received = 0;
    int cycles = 0;
    int supersteps = 0;
    int msgs_sent[num_pe][num_pe];
    int barrier[num_pe];
    for (size_t i = 0; i < num_pe; i++) {
        barrier[i] = 0;
        for (size_t j = 0; j < num_pe; j++) {
            msgs_sent[i][j] = 0;
        }
    }
    while (supersteps < 5){
        for(int i = 0; i < num_pe; i++){
            pe[i]->tick();
            message = pe[i]->getSentMessage();
            if(message){
                if(message->barrier){
                    std::cout << "Distributing barrier from PE " << i << " (round " << supersteps << ")" << std::endl;
                    for(int j = 0; j < num_pe; j++){
                        Message* bm = new Message();
                        bm->roundpar = message->roundpar;
                        bm->barrier = true;
                        bm->dest_id = msgs_sent[i][j];
                        bm->sender = i << PEID_SHIFT;
                        arbiter[j]->putMessage(bm);
                        msgs_sent[i][j] = 0;
                    }
                    delete message;
                    barrier[i]++;
                    int all_barriers = 1;
                    for (size_t j = 0; j < num_pe; j++) {
                        if(!barrier[j]){
                            all_barriers = 0;
                            break;
                        }
                    }
                    if(all_barriers){
                        supersteps++;
                        for (size_t j = 0; j < num_pe; j++) {
                            barrier[j] = 0;
                        }
                    }
                } else {
                    int dest_pe = graph->partition->pe_id(message->dest_id);
                    msgs_sent[i][dest_pe]++;
                    // std::cout << "msgs_sent[" << i << "][" << dest_pe << "] = " << msgs_sent[i][dest_pe] << std::endl;
                    arbiter[dest_pe]->putMessage(message);
                }
            }
            message = arbiter[i]->getMessage();
            if(message){
                pe[i]->putMessageToReceive(message);
                int dest_pe = graph->partition->pe_id(message->dest_id);
                if(message->barrier){
                    std::cout << "Barrier (round " << supersteps << ") for PE " << dest_pe << " from PE " << i << std::endl;
                }

            }
        }
        cycles++;
    }

    exit(0);
}