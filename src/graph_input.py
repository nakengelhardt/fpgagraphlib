import re
import argparse
import logging
from migen import *

logger = logging.getLogger('config')

def read_graph(f, digraph=False, connected=True):
    d = {}
    numbers = {}
    ids = {}
    next_number = 1
    for line in f:
        match = re.match("(\w+)\s(\w+)", line)
        if match:
            source_txt = match.group(1)
            sink_txt = match.group(2)
            if source_txt not in numbers:
                numbers[source_txt] = next_number
                next_number += 1
            if sink_txt not in numbers:
                numbers[sink_txt] = next_number
                next_number += 1
            source = numbers[source_txt]
            ids[source] = source_txt
            sink = numbers[sink_txt]
            ids[sink] = sink_txt
            if source == sink:
                print("Node", source_txt, "linking to itself!")
                continue
            if source not in d:
                d[source] = set()
            if sink not in d:
                d[sink] =  set()
            d[source].add(sink)
            if not digraph:
                d[sink].add(source)
    if connected:
        make_connected(d, digraph=digraph)
    logger.info("Loading input graph with {} nodes and {} edges".format(len(d), sum(len(d[x]) for x in d)))
    return d, ids

def read_graph_balance_pe(f, num_pe, num_nodes_per_pe, digraph=False, connected=True):
    if num_pe == 1:
        return read_graph(f, digraph=digraph, connected=connected)
    d = {}
    numbers = {}
    next_number = 0
    next_pe = 1
    ids = {}
    for line in f:
        match = re.match("(\w+)\s(\w+)", line)
        if match:
            source_txt = match.group(1)
            sink_txt = match.group(2)
            if source_txt not in numbers:
                numbers[source_txt] = next_pe << log2_int(num_nodes_per_pe) | next_number
                next_pe += 1
                if next_pe == num_pe:
                    next_pe = 0
                    next_number += 1
            if sink_txt not in numbers:
                numbers[sink_txt] = next_pe << log2_int(num_nodes_per_pe) | next_number
                next_pe += 1
                if next_pe == num_pe:
                    next_pe = 0
                    next_number += 1
            if next_number >= num_nodes_per_pe:
                logger.error("Graph too big for PE configuration!")
                raise ValueError
            source = numbers[source_txt]
            ids[source] = source_txt
            sink = numbers[sink_txt]
            ids[sink] = sink_txt
            if source == sink:
                logger.warning("Node", source_txt, "linking to itself!")
                continue
            if source not in d:
                d[source] = set()
            if sink not in d:
                d[sink] =  set()
            d[source].add(sink)
            if not digraph:
                d[sink].add(source)
    if connected:
        make_connected(d, digraph=digraph)
    logger.info("Loading input graph with {} nodes and {} edges".format(len(d), sum(len(d[x]) for x in d)))
    for node in d:
        # logger.debug("Vertex {} has {} neighbors: {}".format(ids[node], len(d[node]), [ids[x] for x in d[node]]))
        logger.debug("Vertex {} has {} neighbors: {}".format(node, len(d[node]), d[node]))
    return d, ids

def quick_read_num_nodes_edges(f, digraph=False):
    numbers = {}
    num_seen = 0
    num_edges = 0
    for line in f:
        match = re.match("(\w+)\s(\w+)", line)
        if match:
            source_txt = match.group(1)
            sink_txt = match.group(2)
            if source_txt not in numbers:
                num_seen += 1
                numbers[source_txt] = num_seen
            if sink_txt not in numbers:
                num_seen += 1
                numbers[sink_txt] = num_seen
            if numbers[source_txt] != numbers[sink_txt]:
                num_edges += 1 if digraph else 2
    f.seek(0)
    return num_seen, num_edges


def make_connected(d, init=None, digraph=False):
    if not init:
        init = 1
        while init not in d:
            init += 1
    visited = set()
    to_visit = [init]
    while to_visit:
        node = to_visit.pop()
        if node not in visited:
            to_visit.extend(d[node])
        visited.add(node)
    not_visited = set()
    for node in d:
        if node not in visited:
            d[init].add(node)
            if not digraph:
                d[node].add(init)

def check_connected(d, init=1):
    visited = set()
    to_visit = [init]
    while to_visit:
        node = to_visit.pop()
        if node not in visited:
            to_visit.extend(d[node])
        visited.add(node)
    not_visited = set()
    for node in d:
        if node not in visited:
            not_visited.add(node)
    if not_visited:
        print("Unreachable nodes:", not_visited)
    else:
        print("Graph is connected.")

def max_node_per_pe(adj_dict, num_pe, num_nodes_per_pe):
    max_node = [0 for _ in range(num_pe)]
    for node in adj_dict:
        pe = node//num_nodes_per_pe
        localnode = node % num_nodes_per_pe
        if max_node[pe] < localnode:
            max_node[pe] = localnode
    return max_node

def print_stats(adj_dict, num_pe, num_nodes_per_pe):
    from statistics import mean, stdev
    max_node = max_node_per_pe(adj_dict, num_pe, num_nodes_per_pe)
    adj_idx = [[(0,0) for _ in range(max_node[pe] + 1)] for pe in range(num_pe)]
    adj_val = [[] for _ in range(num_pe)]

    for node, neighbors in adj_dict.items():
        pe = node//num_nodes_per_pe
        localnode = node % num_nodes_per_pe
        idx = len(adj_val[pe])
        n = len(neighbors)
        adj_idx[pe][localnode] = (idx, n)
        adj_val[pe].extend(neighbors)

    print("Nodes per PE: {}".format([len(adj_idx[pe]) for pe in range(num_pe)]))
    edges_pe = [len(adj_val[pe]) for pe in range(num_pe)]
    print("Edges per PE: {}".format(edges_pe))
    print("Mean/stdev Edges: {:G} +/- {:G} ({:%})".format(mean(edges_pe), stdev(edges_pe), stdev(edges_pe)/mean(edges_pe)))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('graphfile', help='filename containing graph')
    parser.add_argument('-d', '--digraph', action="store_true", help='graph is directed (default is undirected)')
    parser.add_argument('-u', '--unconnected', action="store_false", help='do not force graph to be connected (by default an edge from first encountered node to all unreachable nodes is added)')

    parser.add_argument('-b', '--balance', action="store_true", help='round-robin PE assignment')
    parser.add_argument('--pe', nargs=2, type=int, help='num_pe num_nodes_per_pe (for round-robin or stats)')
    parser.add_argument('-s', '--stats', action='store_true', help='print statistics on distribution of edges')
    args = parser.parse_args()

    with open(args.graphfile) as f:
        if(args.balance):
            if not args.pe:
                print("--balance requires --pe num_pe num_nodes_per_pe argument.")
                return -1
            num_pe = args.pe[0]
            num_nodes_per_pe = args.pe[1]
            d = read_graph_balance_pe(f, num_pe, num_nodes_per_pe, digraph=args.digraph, connected=args.unconnected)
        else:
            d = read_graph(f, digraph=args.digraph, connected=args.unconnected)
        if(args.stats):
            if not args.pe:
                print("--stats requires --pe num_pe num_nodes_per_pe argument.")
                return -1
            num_pe = args.pe[0]
            num_nodes_per_pe = args.pe[1]
            print_stats(d, num_pe, num_nodes_per_pe)


if __name__ == "__main__":
    main()
