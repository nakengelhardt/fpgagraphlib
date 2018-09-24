import argparse
import networkx as nx
import nxmetis
import random_connected_graph
from migen import bits_for
import logging

logger = logging.getLogger('config')

def read_graph(path, digraph=False, connected=True):
    g = nx.read_edgelist(path, create_using=nx.DiGraph())
    g = nx.convert_node_labels_to_integers(g, label_attribute="origin")
    g.remove_edges_from(g.selfloop_edges())
    if not digraph:
        for u,v in g.edges():
            g.add_edge(v,u)
    if connected:
        make_connected(g, digraph=digraph)
    return g

def find_cc(g):
    for node in g:
        g.node[node]['cc'] = node
    frontier = set(g.nodes())
    while frontier:
        new_frontier = set()
        for v in frontier:
            for u in g.successors(v):
                if g.node[v]['cc'] < g.node[u]['cc']:
                    g.node[u]['cc'] = g.node[v]['cc']
                    new_frontier.add(u)
        frontier = new_frontier
    ccs = dict()
    for node in g:
        if not g.node[node]['cc'] in ccs:
            ccs[g.node[node]['cc']] = set()
        ccs[g.node[node]['cc']].add(node)
        del g.node[node]['cc']
    return ccs

def make_connected(g, digraph=False):
    ccs = find_cc(g)
    if len(ccs) > 1:
        logger.debug("{} connected components found. Adding edges:".format(len(ccs)))
    for c1 in ccs:
        for c2 in ccs:
            if c1 != c2:
                u = next(iter(ccs[c1]))
                v = next(iter(ccs[c2]))
                logger.debug("{} -- {}".format(u, v))
                g.add_edge(u, v)
                if not digraph:
                    g.add_edge(v, u)

def generate_graph(num_nodes, num_edges, approach="random_walk", digraph=False):
    logger = logging.getLogger('graph_generate')
    logger.debug("Generating {}directed graph with {} nodes and {} edges".format("" if digraph else "un", num_nodes, num_edges))
    fn = getattr(random_connected_graph, approach)
    nodes = list(range(1, num_nodes+1))
    graph = fn(nodes, num_edges, digraph=digraph)
    g = convert_graph(graph, digraph=digraph)
    return g

def convert_graph(graph, digraph=False):
    g = nx.DiGraph()
    g.add_nodes_from(graph.nodes)
    for n1, n2 in graph.edges:
        assert n1 != n2
        g.add_edge(n1, n2)
        if not digraph:
            g.add_edge(n2, n1)
    return d

def export_graph(g, filename):
    write_edgelist(g, filename, data=False)

def partition_metis(g, pe, ufactor=20):
    logger.debug("Dividing into {} partitions, ufactor: {}".format(pe, ufactor))
    ug = g.to_undirected()
    objval, parts = nxmetis.partition(ug, pe, options=nxmetis.MetisOptions(contig=False, ufactor=ufactor))
    logger.debug("Edges crossing: {}, expected from random partition: {}".format(objval , nx.number_of_edges(ug)*(pe-1)/pe))
    logger.debug("Improvement: {}x".format((nx.number_of_edges(ug)*(pe-1)/pe)/objval))
    peid_offset = 1
    for part in parts:
        if peid_offset < bits_for(len(part)):
            peid_offset = bits_for(len(part))

    relabel_d = {}
    for i, part in enumerate(parts):
        for j, n in enumerate(part):
            if i == 0:
                idx = j+1
            else:
                idx = j
            assert idx < 2**peid_offset
            relabel_d[n] = (i << peid_offset) | idx
    g = nx.relabel_nodes(g, relabel_d)
    return g, 2**peid_offset

def partition_random(g, pe):
    num_nodes = nx.number_of_nodes(g)
    peid_offset = bits_for((num_nodes + pe - 1)//pe)
    next_number = 0
    next_pe = 1
    relabel_d = {}
    for n in g.nodes():
        assert next_number < 2**peid_offset
        relabel_d[n] = (next_pe << peid_offset) | next_number
        next_pe += 1
        if next_pe == pe:
            next_pe = 0
            next_number += 1

    g = nx.relabel_nodes(g, relabel_d)
    return g, 2**peid_offset

def make_adj_dict(g):
    d = {}
    for node in g:
        d[node] = list(g.successors(node))
    return d

def print_stats(g):
    print(nx.info(g))
    if nx.number_of_nodes(g) < 30:
        print("Nodes: ", sorted(g.nodes(data=True)))
        print("Edges: ", sorted(g.edges()))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('graphfile', help='filename containing graph')
    parser.add_argument('-d', '--digraph', action="store_true", help='graph is directed (default is undirected)')
    parser.add_argument('-u', '--unconnected', action="store_false", help='do not force graph to be connected (by default an edge from first encountered node to all unreachable nodes is added)')
    parser.add_argument('-b', '--balance', type=int, default=50, help='ufactor for balancing (imbalance may not exceed (1+b)/1000)')
    parser.add_argument('-n', '--nparts', type=int, default=4, help='number of partitions')
    parser.add_argument('-m', '--metis', action="store_true", help='use metis for partitioning (default is random)')
    args = parser.parse_args()

    g = read_graph(args.graphfile, digraph=args.digraph, connected=args.unconnected)
    pe = args.nparts
    if args.metis:
        partition_metis(g, pe, args.balance)
    else:
        partition_random(g, pe)
    print_stats(g)

if __name__ == "__main__":
    main()
