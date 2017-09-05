import re
import argparse
from migen import *

def read_graph(f, digraph=False, connected=True):
    d = {}
    numbers = {}
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
            sink = numbers[sink_txt]
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
        make_connected(d)
    print("Loading input graph with {} nodes and {} edges".format(len(d), sum(len(d[x]) for x in d)))
    return d

def read_graph_balance_pe(f, num_pe, num_nodes_per_pe, digraph=False, connected=True):
    d = {}
    numbers = {}
    next_number = 0
    next_pe = 1
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
                print("Graph too big for PE configuration!")
                raise ValueError
            source = numbers[source_txt]
            sink = numbers[sink_txt]
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
        make_connected(d)
    print("Loading input graph with {} nodes and {} edges".format(len(d), sum(len(d[x]) for x in d)))
    return d

def make_connected(d, init=1, digraph=False):
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
    for node in not_visited:
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

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('graphfile', help='filename containing graph')
    parser.add_argument('-d', '--digraph', action="store_true", help='graph is directed (default is undirected)')
    parser.add_argument('-u', '--unconnected', action="store_false", help='do not force graph to be connected (by default an edge from first encountered node to all unreachable nodes is added)')
    parser.add_argument('-p', '--num-pe', type=int, help="number of PEs to distribute graph nodes over")
    parser.add_argument('-n', '--num-nodes-per-pe', type=int, help="maximum number of nodes allowed per PE")
    args = parser.parse_args()

    with open(args.graphfile) as f:
        if args.num_pe and args.num_nodes_per_pe:
            d = read_graph_balance_pe(f, args.num_pe, args.num_nodes_per_pe, digraph=args.digraph, connected=args.unconnected)
        else:
            d = read_graph(f, digraph=args.digraph, connected=args.unconnected)
        print(d)

if __name__ == "__main__":
    main()
