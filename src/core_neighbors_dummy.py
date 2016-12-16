from migen import *

import logging

from core_interfaces import _neighbor_in_layout, _neighbor_out_layout

class NeighborsDummy(Module):
    def __init__(self, config, adj_val, edge_data=None):
        nodeidsize = config.addresslayout.nodeidsize
        num_nodes_per_pe = config.addresslayout.num_nodes_per_pe
        num_pe = config.addresslayout.num_pe
        edgeidsize = config.addresslayout.edgeidsize
        max_edges_per_pe = config.addresslayout.max_edges_per_pe

        # input
        self.neighbor_in = Record(set_layout_parameters(_neighbor_in_layout, **config.addresslayout.get_params()))

        # output
        self.neighbor_out = Record(set_layout_parameters(_neighbor_out_layout, **config.addresslayout.get_params()))

    def gen_selfcheck(self, tb, graph, quiet=True):
        to_be_sent = [dict() for _ in range(tb.config.addresslayout.num_channels)]
        logger = logging.getLogger('simulation.get_neighbors')
        level = 0
        num_cycles = 0
        while not (yield tb.global_inactive):
            num_cycles += 1
            if (yield self.neighbor_out.barrier):
                level += 1
                rnd = (yield self.neighbor_out.round)
                for sender in to_be_sent[rnd]:
                    if to_be_sent[rnd][sender]:
                        logger.warning("{}: message for nodes {} was not sent from node {}".format(num_cycles, to_be_sent[rnd][sender], sender))
            if (yield self.neighbor_out.valid) and (yield self.neighbor_out.ack):
                neighbor = (yield self.neighbor_out.neighbor)
                curr_sender = (yield self.neighbor_out.sender)
                rnd = (yield self.neighbor_out.round)
                if not quiet:
                    logger.debug("{}: Message from node {} for node {}".format(num_cycles, curr_sender, neighbor))
                    if tb.config.has_edgedata:
                        logger.debug("Edgedata: " + str((yield self.edgedata_out)))
                if (not curr_sender in to_be_sent[rnd]):
                    logger.warning("{}: sending message from node {} whose request was not registered!".format(num_cycles, curr_sender))
                elif (not neighbor in to_be_sent[rnd][curr_sender]):
                    if not neighbor in graph[curr_sender]:
                        logger.warning("{}: sending message to node {} which is not a neighbor of {}!".format(num_cycles, neighbor, curr_sender))
                    else:
                        logger.warning("{}: sending message to node {} more than once from node {}".format(num_cycles, neighbor, curr_sender))
                else:
                    to_be_sent[rnd][curr_sender].remove(neighbor)
            if (yield self.neighbor_in.valid) and (yield self.neighbor_in.ack):
                curr_sender = (yield self.neighbor_in.sender)
                rnd = (yield self.neighbor_in.round)
                logger.debug("{}: request for neighbors of node {}".format(num_cycles, curr_sender))
                if not curr_sender in graph:
                    logger.warning("{}: invalid sender ({})".format(num_cycles, curr_sender))
                else:
                    if curr_sender in to_be_sent[rnd] and to_be_sent[rnd][curr_sender]:
                        logger.warning("{}: message for nodes {} was not sent from node {}".format(num_cycles, to_be_sent[rnd][curr_sender], curr_sender))
                    to_be_sent[rnd][curr_sender] = list(graph[curr_sender])
            yield
