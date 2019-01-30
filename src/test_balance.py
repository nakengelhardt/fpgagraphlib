import argparse
from graph_manage import *

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('graphfile', help='filename containing graph')
    parser.add_argument('-d', '--digraph', action="store_true", help='graph is directed (default is undirected)')
    parser.add_argument('-u', '--unconnected', action="store_false", help='do not force graph to be connected (by default an edge from first encountered node to all unreachable nodes is added)')
    parser.add_argument('-b', '--balance', type=int, default=1, help='ufactor for balancing (imbalance may not exceed (1+b)/1000)')
    parser.add_argument('-n', '--nparts', type=int, default=4, help='number of FPGAs')
    parser.add_argument('-p', '--pe', type=int, default=8, help='number of PEs per FPGA')
    parser.add_argument('-m', '--metis', action="store_true", help='use metis for partitioning (default is random)')
    parser.add_argument('-g', '--greedy', action="store_true", help='use greedy for partitioning (default is random)')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    g = read_graph(args.graphfile, digraph=args.digraph, connected=args.unconnected)
    pe = args.pe
    if args.metis:
        fpga = args.nparts
        g, num_nodes_per_pe = partition_metis(g, fpga, pe, args.balance)
        print_balance(g, pe*fpga, num_nodes_per_pe)
    elif args.greedy:
        g, num_nodes_per_pe = partition_greedyedge(g, pe)
        print_balance(g, pe, num_nodes_per_pe)
    else:
        partition_random(g, pe)
    print_stats(g)

if __name__ == "__main__":
    main()