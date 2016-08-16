"""Generate a randomly connected graph with N nodes and E edges."""

import argparse
import random_connected_graph
import logging

def generate_graph(num_nodes, num_edges, approach="random_walk", digraph=False):
    logger = logging.getLogger('graph_generate')
    logger.debug("Generating {}directed graph with {} nodes and {} edges".format("" if digraph else "un", num_nodes, num_edges))
    fn = getattr(random_connected_graph, approach)
    nodes = list(range(1, num_nodes+1))
    graph = fn(nodes, num_edges, digraph=digraph)
    d = convert_graph(graph, digraph=digraph)
    return d

def convert_graph(graph, digraph=False):
    d = {}
    for n in graph.nodes:
        d[n] = set()
    for n1, n2 in graph.edges:
        assert n1 != n2
        d[n1].add(n2)
        if not digraph:
            d[n2].add(n1)
    return d

def export_graph(d, filename):
    with open(filename, 'w') as f:
        for source in d:
            for sink in d[source]:
                f.write("{} {}\n".format(source, sink))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('nodes', type=int,
                        help='number of nodes to generate')
    parser.add_argument('edges', type=int,
                        help='number of edges')
    parser.add_argument('-r', '--random-walk', action='store_const',
                        const='random_walk', dest='approach',
                        help='use a random-walk generation algorithm (default)')
    parser.add_argument('-n', '--naive', action='store_const',
                        const='naive', dest='approach',
                        help='use a naive generation algorithm (slower)')
    parser.add_argument('-t', '--partition', action='store_const',
                        const='partition', dest='approach',
                        help='use a partition-based generation algorithm (biased)')
    args = parser.parse_args()

    num_nodes = args.nodes
    num_edges = args.edges

    # Approach
    if args.approach:
        print('Setting approach:' + str(args.approach))
        approach = args.approach
    else:
        approach = "random_walk"

    d = generate_graph(num_nodes, num_edges, approach=approach)

    for source in d:
        for sink in d[source]:
            print("{} {}".format(source, sink))

if __name__ == "__main__":
    main()
