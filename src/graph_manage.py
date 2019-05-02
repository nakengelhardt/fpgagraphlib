
import networkx as nx
import nxmetis
import random_connected_graph
from migen import bits_for
import logging
import os
import numpy
from tabulate import tabulate

logger = logging.getLogger('graph_generate')

def read_graph(path, digraph=False, connected=True):
    g = nx.read_edgelist(path, create_using=nx.DiGraph())
    g = nx.convert_node_labels_to_integers(g, label_attribute="origin")
    g.remove_edges_from(g.selfloop_edges())
    if not digraph:
        for u,v in g.edges():
            g.add_edge(v,u)
    if connected:
        make_connected(g, digraph=digraph)
    g.name = os.path.basename(path)
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
    logger.debug("Generating {}directed graph with {} nodes and {} edges".format("" if digraph else "un", num_nodes, num_edges))
    fn = getattr(random_connected_graph, approach)
    nodes = list(range(1, num_nodes+1))
    graph = fn(nodes, num_edges, digraph=digraph)
    g = convert_graph(graph, digraph=digraph)
    g.graph['name'] = "uni_{}V_{}E.graph".format(num_nodes, num_edges)
    return g

def convert_graph(graph, digraph=False):
    g = nx.DiGraph()
    g.add_nodes_from(graph.nodes)
    for n1, n2 in graph.edges:
        assert n1 != n2
        g.add_edge(n1, n2)
        if not digraph:
            g.add_edge(n2, n1)
    return g

def export_graph(g, filename):
    nx.write_edgelist(g, filename, data=False)


def relabel_with_parts(g, parts):
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
    log_stats(g)
    return g, 2**peid_offset

def partition_metis(g, fpga, pe, ufactor=1):
    logger.debug("Dividing into {} partitions, ufactor: {}".format(fpga, ufactor))
    ug = g.to_undirected()
    for node in ug.nodes():
        ug.nodes[node]['weight'] = ug.degree(node)
    objval, fpgaparts = nxmetis.partition(ug, fpga, options=nxmetis.MetisOptions(contig=False, ufactor=ufactor))
    logger.debug("Edges crossing: {} , expected from random partition: {}".format(objval , nx.number_of_edges(ug)*(fpga-1)/fpga))
    logger.debug("Improvement: {}x".format((nx.number_of_edges(ug)*(fpga-1)/fpga)/objval))

    parts = []
    for part in fpgaparts:
        parts.extend(_partition_greedy(g, pe, part))

    return relabel_with_parts(g, parts)

def partition_random(g, pe):
    num_nodes = nx.number_of_nodes(g)
    peid_offset = bits_for((num_nodes + pe - 1)//pe)
    next_number = 0
    next_pe = 1
    relabel_d = {}
    for n in g.nodes():
        if next_pe == pe:
            next_pe = 0
            next_number += 1
        assert next_number < 2**peid_offset
        relabel_d[n] = (next_pe << peid_offset) | next_number
        next_pe += 1

    g = nx.relabel_nodes(g, relabel_d)
    log_stats(g)
    return g, 2**peid_offset

def _partition_greedy(g, pe, nodes):
    parts = [[] for _ in range(pe)]
    edge_len = [0 for _ in range(pe)]
    for n in nodes:
        idx = 0
        min_len = edge_len[0]
        for i in range(1,pe):
            if edge_len[i] < min_len:
                min_len = edge_len[i]
                idx = i
        parts[idx].append(n)
        edge_len[idx] += g.degree(n)
    return parts

def partition_greedyedge(g, pe):
    parts = _partition_greedy(g, pe, g.nodes())
    return relabel_with_parts(g, parts)

def make_adj_dict(g):
    d = {}
    for node in g:
        d[node] = list(g.successors(node))
    return d

def print_balance(g, pe, num_nodes_per_pe):
    vertices = [0 for _ in range(pe)]
    edges = [0 for _ in range(pe)]
    for n in g.nodes():
        pe = n//num_nodes_per_pe
        vertices[pe] += 1
        edges[pe] += g.degree(n)
    print("Vertices per PE: ", vertices)
    print("Edges per PE", edges)

def print_stats(g):
    print(nx.info(g))
    # print("Diameter: {}".format(nx.diameter(g)))
    degrees = numpy.array([g.degree(n) for n in g])
    print("Degree range: {}-{}".format(degrees.min(), degrees.max()))
    print("Standard deviation of degrees: {:.2f}".format(numpy.std(degrees)))
    print("Histogram:")
    # bins = [1 << i for i in range(1,bits_for(int(degrees.max())), 2)]
    hist, bin_edges = numpy.histogram(degrees, bins = 6)#, bins=bins)
    fmt_bin_edges = ["{:.1f}-{:.1f}".format(bin_edges[i], bin_edges[i+1]) for i in range(len(bin_edges)-1)]
    print(tabulate([hist], fmt_bin_edges))

    if nx.number_of_nodes(g) < 30:
        print("Vertices: ", sorted(g.nodes(data=True)))
        print("Edges: ", sorted(g.edges()))

def log_stats(g):
    logger.debug(nx.info(g))
    if nx.number_of_nodes(g) < 30:
        logger.debug("Vertices: {}".format(sorted(g.nodes(data=True))))
        logger.debug("Edges: {}".format(sorted(g.edges())))
