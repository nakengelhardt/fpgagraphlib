import random
import sys
import argparse
import logging
import configparser

from migen import log2_int, bits_for

from graph_input import read_graph
from graph_generate import generate_graph, export_graph

from importlib import import_module

def read_config_files(configfiles='config.ini'):
    config = configparser.ConfigParser()
    config.read(configfiles)
    return config

def parse_cmd_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-c', '--config-file', dest='configfiles',
                        help='filename containing configuration options')
    parser.add_argument('-f', '--from-file', dest='graphfile',
                        help='filename containing graph')
    parser.add_argument('-n', '--nodes', type=int,
                        help='number of nodes to generate')
    parser.add_argument('-e', '--edges', type=int,
                        help='number of edges to generate')
    parser.add_argument('-d', '--digraph', action="store_true", help='graph is directed (default is undirected)')
    parser.add_argument('-s', '--seed', type=int,
                        help='seed to initialise random number generator')
    parser.add_argument('--random-walk', action='store_const',
                        const='random_walk', dest='approach',
                        help='use a random-walk generation algorithm (default)')
    parser.add_argument('--naive', action='store_const',
                        const='naive', dest='approach',
                        help='use a naive generation algorithm (slower)')
    parser.add_argument('--partition', action='store_const',
                        const='partition', dest='approach',
                        help='use a partition-based generation algorithm (biased)')
    parser.add_argument('--save-graph', dest='graphsave', help='save graph to a file')
    parser.add_argument('command', help="one of 'sim' or 'export'")
    parser.add_argument('-o', '--output', help="output file name to save verilog export (valid with command 'export' only)")
    return parser.parse_args()

def init_parse():
    args = parse_cmd_args()

    if args.configfiles:
        config = read_config_files(args.configfiles)
    else:
        config = read_config_files()

    logging.basicConfig(level=config['logging'].get('console_log_level', fallback='DEBUG'),
                        format='%(name)-25s %(levelname)-8s %(message)s',
                        datefmt='%m-%d %H:%M',
                        filename=config['logging'].get('log_file_name', fallback='fpgagraphlib.log'),
                        filemode='w')
    # define a Handler which writes INFO messages or higher to the sys.stderr
    console = logging.StreamHandler()
    console.setLevel(config['logging'].get('file_log_level', fallback='INFO'))
    # set a format which is simpler for console use
    formatter = logging.Formatter('%(name)-25s: %(levelname)-8s %(message)s')
    # tell the handler to use this format
    console.setFormatter(formatter)
    # add the handler to the root logger
    logging.getLogger('').addHandler(console)

    logger = logging.getLogger('config')

    if args.seed:
        s = args.seed
    elif 'seed' in config['graph']:
        s = config['graph'].getint('seed')
    else:
        s = 42
    random.seed(s)

    if args.graphfile:
        logger.info("Reading graph from file {}".format(args.graphfile))
        graphfile = open(args.graphfile)
        adj_dict = read_graph(graphfile)
    elif args.nodes:
        num_nodes = args.nodes
        if args.edges:
            num_edges = args.edges
        else:
            num_edges = num_nodes - 1
        if args.approach:
            approach = args.approach
        else:
            approach = "random_walk"
        logger.info("Generating graph with {} nodes and {} edges".format(num_nodes, num_edges))
        adj_dict = generate_graph(num_nodes, num_edges, approach=approach, digraph=args.digraph)
    elif 'graphfile' in config['graph']:
        graphfile = open(config['graph'].get('graphfile'))
        adj_dict = read_graph(graphfile)
    elif 'nodes' in config['graph']:
        num_nodes = eval(config['graph'].get('nodes'))
        if 'edges' in config['graph']:
            num_edges = eval(config['graph'].get('edges'))
        else:
            num_edges = num_nodes - 1
        if 'approach' in config['graph']:
            approach = config['graph'].get('approach')
        else:
            approach = "random_walk"
        logger.info("Generating graph with {} nodes and {} edges".format(num_nodes, num_edges))
        adj_dict = generate_graph(num_nodes, num_edges, approach=approach, digraph=args.digraph)
    else:
        parser.print_help()
        exit(-1)

    if args.graphsave:
        logger.info("Saving graph to file {}".format(args.graphsave))
        export_graph(adj_dict, args.graphsave)

    algo_config_module = "{}.config".format(config['app']['algo'])
    algo = import_module(algo_config_module)

    kwargs = dict()
    for k in config['arch']:
        kwargs[k] = eval(config['arch'].get(k))

    kwargs["num_channels"] = 4
    kwargs["channel_bits"] = bits_for(kwargs["num_channels"] - 1)

    algo_config = algo.Config(adj_dict, **kwargs)

    logger.info("Algorithm: " + algo_config.name)
    logger.info("Using HMC: " + ("YES" if algo_config.use_hmc else "NO"))
    logger.info("Sharing ports: " + ("YES" if algo_config.share_mem_port else "NO"))
    logger.info("nodeidsize = {}".format(algo_config.addresslayout.nodeidsize))
    logger.info("edgeidsize = {}".format(algo_config.addresslayout.edgeidsize))
    logger.info("peidsize = {}".format(algo_config.addresslayout.peidsize))
    logger.info("num_pe = " + str(algo_config.addresslayout.num_pe))
    logger.info("num_nodes_per_pe = " + str(algo_config.addresslayout.num_nodes_per_pe))
    logger.info("max_edges_per_pe = " + str(algo_config.addresslayout.max_edges_per_pe))
    logger.info("inter_pe_delay =" + str(algo_config.addresslayout.inter_pe_delay))

    return args, algo_config
