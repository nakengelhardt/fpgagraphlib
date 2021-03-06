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

def parse_cmd_args(args, cmd_choices):
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
    parser.add_argument('command', choices=cmd_choices, help="operation to perform")
    parser.add_argument('-o', '--output', help="output file name to save verilog export (valid with command 'export' only)")
    return parser.parse_args(args)

def init_parse(args=None, cmd_choices=("sim", "export"), inverted=None):
    args = parse_cmd_args(args, cmd_choices)

    if args.configfiles:
        config = read_config_files(args.configfiles)
    else:
        config = read_config_files()

    args, algo_config = extract_args(args, config, inverted=inverted)

    logger.info("Algorithm: " + algo_config.name)
    logger.info("Using memory: " + algo_config.memtype)
    logger.info("Using architecture: " + "M" if algo_config.inverted else "S")
    logger.info("nodeidsize = {}".format(algo_config.addresslayout.nodeidsize))
    logger.info("edgeidsize = {}".format(algo_config.addresslayout.edgeidsize))
    logger.info("peidsize = {}".format(algo_config.addresslayout.peidsize))
    logger.info("num_fpga = " + str(algo_config.addresslayout.num_fpga))
    logger.info("num_pe = " + str(algo_config.addresslayout.num_pe))
    logger.info("num_pe_per_fpga = " + str(algo_config.addresslayout.num_pe_per_fpga))
    logger.info("num_nodes_per_pe = " + str(algo_config.addresslayout.num_nodes_per_pe))
    logger.info("max_edges_per_pe = " + str(algo_config.addresslayout.max_edges_per_pe))
    logger.info("Nodes per PE: {}".format([x+1 for x in algo_config.addresslayout.max_node_per_pe(algo_config.adj_dict)]))
    if algo_config.memtype == "BRAM":
        logger.info("Edges per PE: {}".format([(pe, len(algo_config.adj_val[pe])) for pe in range(algo_config.addresslayout.num_pe)]))

    return args, algo_config

class ANSIColorFormatter(logging.Formatter):
    LOG_COLORS = {
        "DEBUG"   : "\033[36m",
        "INFO"    : "\033[0m",
        "WARNING" : "\033[1;33m",
        "ERROR"   : "\033[1;31m",
        "CRITICAL": "\033[1;41m",
    }

    def format(self, record):
        color = self.LOG_COLORS.get(record.levelname, "")
        return "{}{}\033[0m".format(color, super().format(record))

def extract_args(args, config, inverted=None):
    graphfile = None
    num_nodes = None
    num_edges = None
    if args.graphfile:
        graphfile = args.graphfile
    elif args.nodes:
        num_nodes = args.nodes
        if args.edges:
            num_edges = args.edges
        else:
            num_edges = num_nodes - 1

    if args.graphsave:
        graphsave = args.graphsave
    else:
        graphsave = None

    if args.seed:
        s = args.seed
    elif 'seed' in config['graph']:
        s = config['graph'].getint('seed')
    else:
        s = 42
    random.seed(s)

    algo_config = resolve_defaults(config, graphfile=graphfile, num_nodes=num_nodes, num_edges=num_edges, digraph=args.digraph, graphsave=graphsave, sim=(args.command == 'sim'), inverted=inverted)

    return args, algo_config


def resolve_defaults(config, graphfile=None, num_nodes=None, num_edges=None, digraph=False, graphsave=None, sim=True, inverted=None):
    if not graphfile and not num_nodes:
        if 'graphfile' in config['graph']:
            graphfile = config['graph'].get('graphfile')
        elif 'nodes' in config['graph']:
            num_nodes = eval(config['graph'].get('nodes'))
            if not num_edges:
                if 'edges' in config['graph']:
                    num_edges = eval(config['graph'].get('edges'))
                else:
                    num_edges = num_nodes - 1
        else:
            raise ValueError("Graph not specified")
    if 'approach' in config['graph']:
        approach = config['graph'].get('approach')
    else:
        approach = "random_walk"

    graphfile_basename = os.path.splitext(os.path.basename(graphfile))[0] if graphfile else str(num_nodes)
    log_file_basename = "{}_{}_{}".format(config['logging'].get('log_file_name', fallback='fpgagraphlib'), config['app']['algo'], graphfile_basename)

    logger = logging.getLogger()
    logger.setLevel("DEBUG")
    handler = logging.StreamHandler()
    formatter_args = {"fmt": "{levelname:.1s}: {name:>20.20s}: {message:s}", "style": "{"}
    if sys.stderr.isatty() and sys.platform != 'win32':
        handler.setFormatter(ANSIColorFormatter(**formatter_args))
    else:
        handler.setFormatter(logging.Formatter(**formatter_args))
    handler.setLevel(config['logging'].get('console_log_level', fallback='INFO'))
    logger.addHandler(handler)

    log_file_number = 0
    while os.path.exists("{}_{}.log".format(log_file_basename, log_file_number)):
        log_file_number += 1

    alt_adj_val_data_name = None

    if not config['logging'].get('disable_logfile', fallback=False):
        file_log_level = config['logging'].get('file_log_level', fallback='DEBUG')
        logger.info("Logging to file {}_{}.log with level {}".format(log_file_basename, log_file_number, file_log_level))
        # define a Handler which writes INFO messages or higher to the sys.stderr
        logfile = logging.FileHandler(filename="{}_{}.log".format(log_file_basename, log_file_number),
        mode='w')
        logfile.setLevel(file_log_level)
        # set a format which is simpler for console use
        formatter = logging.Formatter('%(levelname)-8s: %(name)-25s: %(message)s')
        # tell the handler to use this format
        logfile.setFormatter(formatter)
        # add the handler to the root logger
        logger.addHandler(logfile)

        alt_adj_val_data_name = "{}_{}.data".format(log_file_basename, log_file_number)

    # root is set up, now get logger for local logging
    logger = logging.getLogger('init')

    kwargs = dict()
    for k in config['arch']:
        try:
            kwargs[k] = eval(config['arch'].get(k))
        except NameError:
            kwargs[k] = config['arch'].get(k)

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

    if graphfile:
        logger.info("Reading graph from file {}".format(graphfile))
        g = read_graph(graphfile, digraph=digraph, connected=True)
        num_nodes = nx.number_of_nodes(g)
        num_edges = nx.number_of_edges(g)
    else:
        logger.info("Generating graph with {} nodes and {} edges".format(num_nodes, num_edges))
        g = generate_graph(num_nodes, num_edges, approach=approach, digraph=digraph)

    if graphsave:
        logger.info("Saving graph to file {}".format(graphsave))
        export_graph(g, graphsave)

    if "memtype" not in kwargs:
        kwargs["memtype"] = "BRAM"
        if "use_hmc" in kwargs:
            logger.warning("\"use_hmc\" is deprecated. Use \"memtype = HMC\" instead.")
            if kwargs["use_hmc"]:
                kwargs["memtype"] = "HMC"
        if "use_ddr" in kwargs:
            logger.warning("\"use_ddr\" is deprecated. Use \"memtype = AXI\" instead.")
            if kwargs["use_ddr"]:
                kwargs["memtype"] = "AXI"

    if "updates_in_hmc" not in kwargs:
        kwargs["updates_in_hmc"] = False

    if inverted != None:
        kwargs["inverted"] = inverted
    elif "arch" in kwargs:
        if kwargs["arch"] == "S":
            kwargs["inverted"] = False
        elif kwargs["arch"] == "M":
            kwargs["inverted"] = True
        else:
            ValueError("Unknown architecture \"{}\"".format(kwargs["arch"]))
    else:
        kwargs["inverted"] = (kwargs["num_fpga"] > 1)

    if kwargs["memtype"] == "HMC" and kwargs["updates_in_hmc"]:
        raise NotImplementedError("Can't use HMC for edges in 2-phase mode")

    updates_in_hmc = kwargs["updates_in_hmc"] if "updates_in_hmc" in kwargs else False

    if "num_nodes_per_pe" in kwargs or "max_edges_per_pe" in kwargs:
        logger.warning("Setting num_nodes_per_pe or max_edges_per_pe manually is no longer supported! Value ignored.")

    if 'partition' in config['graph']:
        kwargs["partition"] = config['graph'].get('partition')
        if 'partition_ufactor' in config['graph']:
            kwargs["partition_ufactor"] = config['graph'].getint('partition_ufactor')
        else:
            kwargs["partition_ufactor"] = 1
    else:
        kwargs["partition"] = "robin"

    if "peidsize" not in kwargs:
        kwargs["peidsize"] = bits_for(kwargs["num_pe"])

    algo_config_module = "{}.config".format(config['app']['algo'])
    algo = import_module(algo_config_module)

    algo_config = algo.Config(g, **kwargs)

    if config['logging'].get('disable_logfile', fallback=False):
        algo_config.vcdname = None
    else:
        algo_config.vcdname = "{}_{}".format(log_file_basename, log_file_number)

    algo_config.alt_adj_val_data_name = alt_adj_val_data_name

    algo_config.hmc_fifo_bits = 20 if sim else 32-bits_for(algo_config.addresslayout.num_pe-1)

    for pe in range(algo_config.addresslayout.num_pe):
        if not kwargs["inverted"]:
            assert len(algo_config.adj_idx[pe]) <= algo_config.addresslayout.num_nodes_per_pe
            assert len(algo_config.adj_idx[pe]) <= 2**(algo_config.addresslayout.nodeidsize - algo_config.addresslayout.peidsize)
        if algo_config.memtype == "BRAM":
            assert len(algo_config.adj_val[pe]) <= algo_config.addresslayout.max_edges_per_pe

    return algo_config
