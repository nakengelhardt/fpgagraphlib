from migen.fhdl import verilog
from core_init import init_parse

def main():
    args, config = init_parse()

    gatherkernel = config.gatherkernel(config.addresslayout)

    ios = {
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
                    name=config.name + "_gather",
                    ios=ios
                    ).write(config.name + "_gather.v")

    applykernel = config.applykernel(config.addresslayout)

    ios = {
        applykernel.nodeid_in,
        applykernel.valid_in,
        applykernel.barrier_in,
        applykernel.round_in,
        applykernel.ready,
        applykernel.nodeid_out,
        applykernel.state_valid,
        applykernel.state_barrier,
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
                    name=config.name + "_apply",
                    ios=ios
                    ).write(config.name + "_apply.v")

    scatterkernel = config.scatterkernel(config.addresslayout)

    ios = {
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

    verilog.convert(scatterkernel,
                    name=config.name + "_scatter",
                    ios=ios
                    ).write(config.name + "_scatter.v")

if __name__ == '__main__':
    main()
