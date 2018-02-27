import random
import sys
import argparse
import logging
import configparser

from migen import log2_int, bits_for

from graph_input import read_graph_balance_pe, quick_read_num_nodes_edges
from graph_generate import generate_graph, export_graph

from importlib import import_module

def read_config_files(configfiles='config.ini'):
    config = configparser.ConfigParser()
    config.read(configfiles)
    return config

def parse_cmd_args(args=None):
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
    return parser.parse_args(args)

def init_parse(args=None):
    args = parse_cmd_args(args)

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

    kwargs = dict()
    for k in config['arch']:
        kwargs[k] = eval(config['arch'].get(k))

    if "num_channels" not in kwargs:
        kwargs["num_channels"] = 3

    kwargs["channel_bits"] = bits_for(kwargs["num_channels"] - 1)

    if "num_fpga" not in kwargs:
        if "num_pe_per_fpga" in kwargs and "num_pe" in kwargs:
            kwargs["num_fpga"] = (kwargs["num_pe"] + kwargs["num_pe_per_fpga"] - 1)//kwargs["num_pe_per_fpga"]
        else:
            kwargs["num_fpga"] = 1

    if "num_pe" not in kwargs:
        if "num_pe_per_fpga" in kwargs:
            kwargs["num_pe"] = kwargs["num_pe_per_fpga"]*kwargs["num_fpga"]
        else:
            kwargs["num_pe"] = 8

    if "num_pe_per_fpga" not in kwargs:
        kwargs["num_pe_per_fpga"] = (kwargs["num_pe"] + kwargs["num_fpga"] - 1)//kwargs["num_fpga"]

    graphfile = None
    if args.graphfile:
        graphfile = open(args.graphfile)
        num_nodes, num_edges = quick_read_num_nodes_edges(graphfile, digraph=args.digraph)
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
    elif 'graphfile' in config['graph']:
        graphfile = open(config['graph'].get('graphfile'))
        num_nodes, num_edges = quick_read_num_nodes_edges(graphfile)
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
    else:
        parser.print_help()
        exit(-1)

    if "num_nodes_per_pe" not in kwargs:
        kwargs["num_nodes_per_pe"] = 2**bits_for((num_nodes + kwargs["num_pe"] - 1)//kwargs["num_pe"])
    assert kwargs["num_nodes_per_pe"]*kwargs["num_pe"] > num_nodes #strictly greater to account for 0 not being valid id

    if "max_edges_per_pe" not in kwargs:
        kwargs["max_edges_per_pe"] = 2**bits_for(num_edges) #very conservative

    if graphfile:
        logger.info("Reading graph from file {}".format(graphfile.name))
        adj_dict = read_graph_balance_pe(graphfile, kwargs["num_pe"], kwargs["num_nodes_per_pe"], digraph=args.digraph)
    else:
        logger.info("Generating graph with {} nodes and {} edges".format(num_nodes, num_edges))
        adj_dict = generate_graph(num_nodes, num_edges, approach=approach, digraph=args.digraph)

    if args.graphsave:
        logger.info("Saving graph to file {}".format(args.graphsave))
        export_graph(adj_dict, args.graphsave)

    if "peidsize" not in kwargs:
        kwargs["peidsize"] = bits_for(kwargs["num_pe"])

    if "nodeidsize" not in kwargs:
        kwargs["nodeidsize"] = kwargs["peidsize"] + log2_int(kwargs["num_nodes_per_pe"])

    if "edgeidsize" not in kwargs:
        kwargs["edgeidsize"] = log2_int(kwargs["max_edges_per_pe"])

    algo_config_module = "{}.config".format(config['app']['algo'])
    algo = import_module(algo_config_module)

    use_hmc = kwargs["use_hmc"] if "use_hmc" in kwargs else False
    use_ddr = kwargs["use_ddr"] if "use_ddr" in kwargs else False
    share_mem_port = kwargs["share_mem_port"] if "share_mem_port" in kwargs else False

    algo_config = algo.Config(adj_dict, **kwargs)

    algo_config.use_hmc = use_hmc
    algo_config.use_ddr = use_ddr
    algo_config.share_mem_port = share_mem_port
    if use_hmc:
        assert not algo_config.has_edgedata
        adj_idx, adj_val = algo_config.addresslayout.generate_partition_flat(adj_dict, edges_per_burst=4)
    elif use_ddr:
        assert not algo_config.has_edgedata
        adj_idx, adj_val = algo_config.addresslayout.generate_partition_flat(adj_dict, edges_per_burst=16)
    else:
        adj_idx, adj_val = algo_config.addresslayout.generate_partition(adj_dict)
    algo_config.adj_idx = adj_idx
    algo_config.adj_val = adj_val

    for pe in range(kwargs["num_pe"]):
        assert len(algo_config.adj_idx[pe]) <= kwargs["num_nodes_per_pe"]
        if not algo_config.use_hmc and not algo_config.use_ddr:
            assert len(algo_config.adj_val[pe]) <= kwargs["max_edges_per_pe"]

    logger.info("Algorithm: " + algo_config.name)
    logger.info("Using memory: " + ("HMC" if algo_config.use_hmc else "DDR" if algo_config.use_ddr else "BRAM"))
    logger.info("nodeidsize = {}".format(algo_config.addresslayout.nodeidsize))
    logger.info("edgeidsize = {}".format(algo_config.addresslayout.edgeidsize))
    logger.info("peidsize = {}".format(algo_config.addresslayout.peidsize))
    logger.info("num_fpga = " + str(algo_config.addresslayout.num_fpga))
    logger.info("num_pe = " + str(algo_config.addresslayout.num_pe))
    logger.info("num_pe_per_fpga = " + str(algo_config.addresslayout.num_pe_per_fpga))
    logger.info("num_nodes_per_pe = " + str(algo_config.addresslayout.num_nodes_per_pe))
    logger.info("max_edges_per_pe = " + str(algo_config.addresslayout.max_edges_per_pe))
    logger.info("Nodes per PE: {}".format([len(algo_config.adj_idx[pe]) for pe in range(algo_config.addresslayout.num_pe)]))
    if not algo_config.use_hmc and not algo_config.use_ddr:
        logger.info("Edges per PE: {}".format([(pe, len(algo_config.adj_val[pe])) for pe in range(algo_config.addresslayout.num_pe)]))

    return args, algo_config
