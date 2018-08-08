from migen import *
from migen.fhdl import verilog
from core_init import init_parse

def GatherApplyScatter(config):

    gatherkernel = config.gatherkernel(config)
    gatherkernel.clock_domains.cd_sys = ClockDomain()

    ios = {
        gatherkernel.cd_sys.clk,
        gatherkernel.cd_sys.rst,
        gatherkernel.level_in,
        gatherkernel.nodeid_in,
        gatherkernel.sender_in,
        gatherkernel.valid_in,
        gatherkernel.ready,
        gatherkernel.nodeid_out,
        gatherkernel.state_valid,
        gatherkernel.state_ack
    }

    ios |= set(getattr(gatherkernel.message_in, s[0]) for s in gatherkernel.message_in.layout)
    ios |= set(getattr(gatherkernel.state_in, s[0]) for s in gatherkernel.state_in.layout)
    ios |= set(getattr(gatherkernel.state_out, s[0]) for s in gatherkernel.state_out.layout)

    verilog.convert(gatherkernel,
                    name="gather",
                    ios=ios
                    ).write("gather.v")

    applykernel = config.applykernel(config)
    applykernel.clock_domains.cd_sys = ClockDomain()

    ios = {
        applykernel.cd_sys.clk,
        applykernel.cd_sys.rst,
        applykernel.nodeid_in,
        applykernel.valid_in,
        applykernel.state_in_valid,
        applykernel.barrier_in,
        applykernel.round_in,
        applykernel.ready,
        applykernel.nodeid_out,
        applykernel.state_valid,
        applykernel.state_barrier,
        applykernel.state_ack,
        applykernel.update_sender,
        applykernel.update_valid,
        applykernel.update_round,
        applykernel.barrier_out,
        applykernel.update_ack
    }

    ios |= set(getattr(applykernel.state_in, s[0]) for s in applykernel.state_in.layout)
    ios |= set(getattr(applykernel.state_out, s[0]) for s in applykernel.state_out.layout)
    ios |= set(getattr(applykernel.update_out, s[0]) for s in applykernel.update_out.layout)

    verilog.convert(applykernel,
                    name="apply",
                    ios=ios
                    ).write("apply.v")

    scatterkernel = config.scatterkernel(config)
    scatterkernel.clock_domains.cd_sys = ClockDomain()

    ios = {
        scatterkernel.cd_sys.clk,
        scatterkernel.cd_sys.rst,
        scatterkernel.num_neighbors_in,
        scatterkernel.neighbor_in,
        scatterkernel.sender_in,
        scatterkernel.round_in,
        scatterkernel.barrier_in,
        scatterkernel.valid_in,
        scatterkernel.ready,
        scatterkernel.neighbor_out,
        scatterkernel.sender_out,
        scatterkernel.round_out,
        scatterkernel.valid_out,
        scatterkernel.message_ack,
        scatterkernel.barrier_out
    }

    ios |= set(getattr(scatterkernel.update_in, s[0]) for s in scatterkernel.update_in.layout)
    ios |= set(getattr(scatterkernel.message_out, s[0]) for s in scatterkernel.message_out.layout)

    if(config.has_edgedata):
        ios |= set(getattr(scatterkernel.edgedata_in, s[0]) for s in scatterkernel.edgedata_in.layout)

    verilog.convert(scatterkernel,
                    name="scatter",
                    ios=ios
                    ).write("scatter.v")

def MixedGAS(config):

    gatherapplykernel = config.gatherapplykernel(config)
    gatherapplykernel.clock_domains.cd_sys = ClockDomain()

    ios = {
        gatherapplykernel.cd_sys.clk,
        gatherapplykernel.cd_sys.rst,
        gatherapplykernel.level_in,
        gatherapplykernel.nodeid_in,
        gatherapplykernel.sender_in,
        gatherapplykernel.message_in_valid,
        gatherapplykernel.state_in_valid,
        gatherapplykernel.round_in,
        gatherapplykernel.barrier_in,
        gatherapplykernel.valid_in,
        gatherapplykernel.ready,

        gatherapplykernel.nodeid_out,
        gatherapplykernel.state_barrier,
        gatherapplykernel.state_valid,
        gatherapplykernel.state_ack,

        gatherapplykernel.update_sender,
        gatherapplykernel.update_round,
        gatherapplykernel.barrier_out,
        gatherapplykernel.update_valid,
        gatherapplykernel.update_ack,

        gatherapplykernel.kernel_error
    }

    ios |= set(getattr(gatherapplykernel.message_in, s[0]) for s in gatherapplykernel.message_in.layout)
    ios |= set(getattr(gatherapplykernel.state_in, s[0]) for s in gatherapplykernel.state_in.layout)
    ios |= set(getattr(gatherapplykernel.state_out, s[0]) for s in gatherapplykernel.state_out.layout)
    ios |= set(getattr(gatherapplykernel.update_out, s[0]) for s in gatherapplykernel.update_out.layout)

    verilog.convert(gatherapplykernel,
                    name="gatherapply",
                    ios=ios
                    ).write("gatherapply.v")

    scatterkernel = config.scatterkernel(config)
    scatterkernel.clock_domains.cd_sys = ClockDomain()

    ios = {
        scatterkernel.cd_sys.clk,
        scatterkernel.cd_sys.rst,
        scatterkernel.num_neighbors_in,
        scatterkernel.neighbor_in,
        scatterkernel.sender_in,
        scatterkernel.round_in,
        scatterkernel.barrier_in,
        scatterkernel.valid_in,
        scatterkernel.ready,
        scatterkernel.neighbor_out,
        scatterkernel.sender_out,
        scatterkernel.round_out,
        scatterkernel.valid_out,
        scatterkernel.message_ack,
        scatterkernel.barrier_out
    }

    ios |= set(getattr(scatterkernel.update_in, s[0]) for s in scatterkernel.update_in.layout)
    ios |= set(getattr(scatterkernel.message_out, s[0]) for s in scatterkernel.message_out.layout)

    if(config.has_edgedata):
        ios |= set(getattr(scatterkernel.edgedata_in, s[0]) for s in scatterkernel.edgedata_in.layout)

    verilog.convert(scatterkernel,
                    name="scatter",
                    ios=ios
                    ).write("scatter.v")


def main():
    args, config = init_parse()
    if hasattr(config, "gatherapplykernel"):
        MixedGAS(config)
    else:
        GatherApplyScatter(config)

if __name__ == '__main__':
    main()
