from graph_manage import *
import argparse
import random

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--from-file', dest='graphfile',
                        help='filename containing graph')
    parser.add_argument('-n', '--nodes', type=int,
                        help='number of nodes to generate')
    parser.add_argument('-e', '--edges', type=int,
                        help='number of edges to generate')
    parser.add_argument('-d', '--digraph', action="store_true", help='graph is directed (default is undirected)')
    parser.add_argument('-c', '--connected', action="store_false", help='graph is directed (default is undirected)')
    parser.add_argument('-s', '--seed', type=int,
                        help='seed to initialise random number generator')

    parser.add_argument('-o', '--save-graph', dest='graphsave', help='save graph to a file')
    
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    if args.graphfile:
        g = read_graph(args.graphfile, digraph=args.digraph, connected=args.connected)
    elif args.nodes:
        num_nodes = args.nodes
        if args.edges:
            num_edges = args.edges
        else:
            num_edges = num_nodes - 1

        g = generate_graph(num_nodes, num_edges, digraph=args.digraph)
        if args.connected:
            make_connected(g, digraph=args.digraph)

        if args.seed:
            s = args.seed
        else:
            s = 42
        random.seed(s)

    print_stats(g)

    if args.graphsave:
        logger.info("Saving graph to file {}".format(args.graphsave))
        export_graph(g, args.graphsave)


        


if __name__ == "__main__":
    main()