from migen import *

to_be_sent = dict()

class NeighborsDummy(Module):
    def __init__(self, config, adj_val, edge_data=None):
        nodeidsize = config.addresslayout.nodeidsize
        num_nodes_per_pe = config.addresslayout.num_nodes_per_pe
        num_pe = config.addresslayout.num_pe
        edgeidsize = config.addresslayout.edgeidsize
        max_edges_per_pe = config.addresslayout.max_edges_per_pe

        # input
        self.start_idx = Signal(edgeidsize)
        self.num_neighbors = Signal(edgeidsize)
        self.valid = Signal()
        self.ack = Signal()
        self.barrier_in = Signal()
        self.message_in = Signal(config.addresslayout.payloadsize)
        self.sender_in = Signal(config.addresslayout.nodeidsize)
        self.round_in = Signal()

        # output
        self.neighbor = Signal(nodeidsize)
        self.neighbor_valid = Signal()
        self.neighbor_ack = Signal()
        self.barrier_out = Signal()
        self.message_out = Signal(config.addresslayout.payloadsize)
        self.sender_out = Signal(config.addresslayout.nodeidsize)
        self.round_out = Signal()
        self.num_neighbors_out = Signal(edgeidsize)

    def gen_selfcheck(self, tb, graph, quiet=True):
        level = 0
        num_cycles = 0
        while not (yield tb.global_inactive):
            num_cycles += 1
            if (yield self.barrier_out):
                level += 1
            if (yield self.neighbor_valid) and (yield self.neighbor_ack):
                neighbor = (yield self.neighbor)
                curr_sender = (yield self.sender_out)
                if not quiet:
                    print("{}\tMessage from node {} for node {}".format(num_cycles, curr_sender, neighbor))
                    if tb.config.has_edgedata:
                        print("Edgedata: " + str((yield self.edgedata_out)))
                if (not curr_sender in to_be_sent):
                    print("{}\tWarning: sending message from node {} whose request was not registered!".format(num_cycles, curr_sender))
                elif (not neighbor in to_be_sent[curr_sender]):
                    if not neighbor in graph[curr_sender]:
                        print("{}\tWarning: sending message to node {} which is not a neighbor of {}!".format(num_cycles, neighbor, curr_sender))
                    else:
                        print("{}\tWarning: sending message to node {} more than once from node {}".format(num_cycles, neighbor, curr_sender))
                else:
                    to_be_sent[curr_sender].remove(neighbor)
            if (yield self.valid) and (yield self.ack):
                curr_sender = (yield self.sender_in)
                print("get_neighbor: request for neighbors of node {}".format(curr_sender))
                if not curr_sender in graph:
                    print("{}\tWarning: invalid sender ({})".format(num_cycles, curr_sender))
                else:
                    if curr_sender in to_be_sent and to_be_sent[curr_sender]:
                        print("{}\tWarning: message for nodes {} was not sent from node {}".format(num_cycles, to_be_sent[curr_sender], curr_sender))
                    to_be_sent[curr_sender] = list(graph[curr_sender])
            yield
