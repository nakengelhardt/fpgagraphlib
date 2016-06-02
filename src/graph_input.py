import re
import argparse

def read_graph(f, digraph=False):
    # print("Loading input graph...")
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
    # print(d)
    # print("...done.")
    return d

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
    args = parser.parse_args()

    with open(args.graphfile) as f:
        d = read_graph(f, digraph=args.digraph)
        check_connected(d)

if __name__ == "__main__":
    main()