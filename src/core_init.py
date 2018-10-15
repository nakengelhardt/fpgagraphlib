import random
import sys
import argparse
import logging
import configparser
import os

from migen import log2_int, bits_for

from graph_manage import *

from importlib import import_module

logger = logging.getLogger('config')

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
    parser.add_argument('--save-graph', dest='graphsave', help='save graph to a file')
    parser.add_argument('command', help="one of 'sim' or 'export'")
    parser.add_argument('-o', '--output', help="output file name to save verilog export (valid with command 'export' only)")
    return parser.parse_args(args)

def max_edges_per_pe(adj_dict, num_pe, num_nodes_per_pe):
    max_pe = [0 for _ in range(num_pe)]
    for node in adj_dict:
        pe = node >> log2_int(num_nodes_per_pe)
        max_pe[pe] += len(adj_dict[node])
    return max(max_pe)

def init_parse(args=None, inverted=False):
    args = parse_cmd_args(args)

    if args.configfiles:
        config = read_config_files(args.configfiles)
    else:
        config = read_config_files()

    args, algo_config = resolve_defaults(args, config, inverted)



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
    logger.info("Nodes per PE: {}".format([x+1 for x in algo_config.addresslayout.max_node_per_pe(algo_config.adj_dict)]))
    if not algo_config.use_hmc and not algo_config.use_ddr:
        logger.info("Edges per PE: {}".format([(pe, len(algo_config.adj_val[pe])) for pe in range(algo_config.addresslayout.num_pe)]))

    return args, algo_config

class ANSIColorFormatter(logging.Formatter):
    LOG_COLORS = {
        "DEBUG"   : "\033[36m",
        "INFO"    : "\033[37m",
        "WARNING" : "\033[1;33m",
        "ERROR"   : "\033[1;31m",
        "CRITICAL": "\033[1;41m",
    }

    def format(self, record):
        color = self.LOG_COLORS.get(record.levelname, "")
        return "{}{}\033[0m".format(color, super().format(record))

def resolve_defaults(args, config, inverted):
    graphfile_basename = os.path.basename(args.graphfile if args.graphfile else config['graph'].get('graphfile') if 'graphfile' in config['graph'] else args.nodes if args.nodes else config['graph'].get('nodes')).split(".", 1)[0]
    log_file_basename = "{}_{}_{}".format(config['logging'].get('log_file_name', fallback='fpgagraphlib'), config['app']['algo'], graphfile_basename)

    logger = logging.getLogger()
    logger.setLevel(config['logging'].get('console_log_level', fallback='INFO'))
    handler = logging.StreamHandler()
    formatter_args = {"fmt": "{levelname:.1s}: {name:>20.20s}: {message:s}", "style": "{"}
    if sys.stderr.isatty() and sys.platform != 'win32':
        handler.setFormatter(ANSIColorFormatter(**formatter_args))
    else:
        handler.setFormatter(logging.Formatter(**formatter_args))
    logger.addHandler(handler)

    log_file_number = 0
    while os.path.exists("{}_{}.log".format(log_file_basename, log_file_number)):
        log_file_number += 1

    if not config['logging'].get('disable_logfile', fallback=False):
        logger.info("Logging to file {}_{}.log".format(log_file_basename, log_file_number))
        # define a Handler which writes INFO messages or higher to the sys.stderr
        logfile = logging.FileHandler(filename="{}_{}.log".format(log_file_basename, log_file_number),
        mode='w')
        logfile.setLevel(config['logging'].get('file_log_level', fallback='DEBUG'))
        # set a format which is simpler for console use
        formatter = logging.Formatter('%(levelname)-8s: %(name)-25s: %(message)s')
        # tell the handler to use this format
        logfile.setFormatter(formatter)
        # add the handler to the root logger
        logger.addHandler(logfile)

    # root is set up, now get logger for local logging
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
        graphfile = args.graphfile
    elif args.nodes:
        num_nodes = args.nodes
        if args.edges:
            num_edges = args.edges
        else:
            num_edges = num_nodes - 1
        approach = "random_walk"
    elif 'graphfile' in config['graph']:
        graphfile = config['graph'].get('graphfile')
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

    if graphfile:
        logger.info("Reading graph from file {}".format(graphfile))
        g = read_graph(graphfile, digraph=args.digraph, connected=True)
        num_nodes = nx.number_of_nodes(g)
        num_edges = nx.number_of_edges(g)
    else:
        logger.info("Generating graph with {} nodes and {} edges".format(num_nodes, num_edges))
        g = generate_graph(num_nodes, num_edges, approach=approach, digraph=args.digraph)

    if args.graphsave:
        logger.info("Saving graph to file {}".format(args.graphsave))
        export_graph(g, args.graphsave)

    use_hmc = kwargs["use_hmc"] if "use_hmc" in kwargs else False
    use_ddr = kwargs["use_ddr"] if "use_ddr" in kwargs else False
    updates_in_hmc = kwargs["updates_in_hmc"] if "updates_in_hmc" in kwargs else False

    if "num_nodes_per_pe" in kwargs:
        logger.warning("No longer supporting setting num_nodes_per_pe manually! Value ignored.")

    if 'partition' in config['graph'] and config['graph'].get('partition') == "metis":
        if 'partition_ufactor' in config['graph']:
            ufactor = config['graph'].getint('partition_ufactor')
        else:
            ufactor = 20
        g, kwargs["num_nodes_per_pe"] = partition_metis(g, kwargs["num_pe"], ufactor=ufactor)
    else:
        g, kwargs["num_nodes_per_pe"] = partition_random(g, kwargs["num_pe"])

    adj_dict = make_adj_dict(g)

    if "max_edges_per_pe" not in kwargs:
        if not use_ddr and not use_hmc:
            kwargs["max_edges_per_pe"] = 2**bits_for(max_edges_per_pe(adj_dict, kwargs["num_pe"], kwargs["num_nodes_per_pe"]))
        else:
            kwargs["max_edges_per_pe"] = 2**bits_for(num_edges-1)

    if "peidsize" not in kwargs:
        kwargs["peidsize"] = bits_for(kwargs["num_pe"])

    if "nodeidsize" not in kwargs:
        kwargs["nodeidsize"] = kwargs["peidsize"] + log2_int(kwargs["num_nodes_per_pe"])

    if "edgeidsize" not in kwargs:
        if use_ddr:
            kwargs["edgeidsize"] = 33
        elif use_hmc:
            kwargs["edgeidsize"] = 34
        else:
            kwargs["edgeidsize"] = log2_int(kwargs["max_edges_per_pe"])

    algo_config_module = "{}.config".format(config['app']['algo'])
    algo = import_module(algo_config_module)

    algo_config = algo.Config(adj_dict, **kwargs)
    algo_config.graph = g

    if config['logging'].get('disable_logfile', fallback=False):
        algo_config.vcdname = None
    else:
        algo_config.vcdname = "{}_{}".format(log_file_basename, log_file_number)

    algo_config.use_hmc = use_hmc
    algo_config.use_ddr = use_ddr
    algo_config.updates_in_hmc = updates_in_hmc
    algo_config.inverted = inverted
    if inverted:
        if use_hmc:
            assert not algo_config.has_edgedata
            adj_idx, adj_val = algo_config.addresslayout.generate_partition_flat_inverted(adj_dict, edges_per_burst=4)
        elif use_ddr:
            assert not algo_config.has_edgedata
            adj_idx, adj_val = algo_config.addresslayout.generate_partition_flat_inverted(adj_dict, edges_per_burst=16)
        else:
            adj_idx, adj_val = algo_config.addresslayout.generate_partition_inverted(adj_dict)
    else:
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
    algo_config.start_addr = (1<<34)
    algo_config.hmc_fifo_bits = 20 if args.command=='sim' else 32-bits_for(algo_config.addresslayout.num_pe-1)

    for pe in range(algo_config.addresslayout.num_pe):
        if not inverted:
            assert len(algo_config.adj_idx[pe]) <= algo_config.addresslayout.num_nodes_per_pe
            assert len(algo_config.adj_idx[pe]) <= 2**(algo_config.addresslayout.nodeidsize - algo_config.addresslayout.peidsize)
        if not algo_config.use_hmc and not algo_config.use_ddr:
            assert len(algo_config.adj_val[pe]) <= algo_config.addresslayout.max_edges_per_pe

    return args, algo_config
