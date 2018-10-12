from migen import *
from migen.genlib.record import *
from importlib import import_module

def _add_fields(signals, record, dir):
    for field in record.layout:
        if len(field) > 2 and field[2] == DIR_S_TO_M:
            if dir == "i":
                dir = "o"
            elif dir == "o":
                dir = "i"
            else:
                raise ValueError("'dir' needs to be either 'i' or 'o'")
        signals["{}_{}_{}".format(dir, record.name, field[0])] = getattr(record, field[0])

class NetlistGatherKernelWrapper(Module):
    def __init__(self, config):
        interfaces = import_module("{}.interfaces".format(config.name))

        self.level_in = Signal(32)
        self.nodeid_in = Signal(config.addresslayout.nodeidsize)
        self.sender_in = Signal(config.addresslayout.nodeidsize)
        self.message_in = Record(set_layout_parameters(interfaces.payload_layout, **config.addresslayout.get_params()))
        self.state_in = Record(set_layout_parameters(interfaces.node_storage_layout, **config.addresslayout.get_params()))
        self.valid_in = Signal()
        self.ready = Signal()

        self.nodeid_out = Signal(config.addresslayout.nodeidsize)
        self.state_out = Record(set_layout_parameters(interfaces.node_storage_layout, **config.addresslayout.get_params()))
        self.state_valid = Signal()
        self.state_ack = Signal()

        signals = {}
        signals["i_sys_clk"] = ClockSignal()
        # signals["i_sys_rst"] = ResetSignal()

        signals["i_level_in"] = self.level_in
        signals["i_nodeid_in"] = self.nodeid_in
        signals["i_sender_in"] = self.sender_in
        _add_fields(signals, self.message_in, "i")
        _add_fields(signals, self.state_in, "i")
        signals["i_valid_in"] = self.valid_in
        signals["o_ready"] = self.ready

        signals["o_nodeid_out"] = self.nodeid_out
        _add_fields(signals, self.state_out, "o")
        signals["o_state_valid"] = self.state_valid
        signals["i_state_ack"] = self.state_ack

        self.specials += Instance("{}_gather".format(config.name), **signals)

class NetlistApplyKernelWrapper(Module):
    def __init__(self, config):
        interfaces = import_module("{}.interfaces".format(config.name))

        self.nodeid_in = Signal(config.addresslayout.nodeidsize)
        self.state_in = Record(set_layout_parameters(interfaces.node_storage_layout, **config.addresslayout.get_params()))
        self.state_in_valid = Signal()
        self.valid_in = Signal()
        self.round_in = Signal(config.addresslayout.channel_bits)
        self.barrier_in = Signal()
        self.ready = Signal()

        self.nodeid_out = Signal(config.addresslayout.nodeidsize)
        self.state_out = Record(set_layout_parameters(interfaces.node_storage_layout, **config.addresslayout.get_params()))
        self.state_valid = Signal()
        self.state_barrier = Signal()
        self.state_ack = Signal()

        self.update_out = Record(set_layout_parameters(interfaces.payload_layout, **config.addresslayout.get_params()))
        self.update_sender = Signal(config.addresslayout.nodeidsize)
        self.update_valid = Signal()
        self.update_round = Signal(config.addresslayout.channel_bits)
        self.barrier_out = Signal()
        self.update_ack = Signal()

        self.kernel_error = Signal()


        signals = {}
        signals["i_sys_clk"] = ClockSignal()
        # signals["i_sys_rst"] = ResetSignal()

        signals["i_nodeid_in"] = self.nodeid_in
        _add_fields(signals, self.state_in, "i")
        signals["i_state_in_valid"] = self.state_in_valid
        signals["i_valid_in"] = self.valid_in
        signals["i_round_in"] = self.round_in
        signals["i_barrier_in"] = self.barrier_in
        signals["o_ready"] = self.ready

        signals["o_nodeid_out"] = self.nodeid_out
        _add_fields(signals, self.state_out, "o")
        signals["o_state_valid"] = self.state_valid
        signals["o_state_barrier"] = self.state_barrier
        signals["i_state_ack"] = self.state_ack

        _add_fields(signals, self.update_out, "o")
        signals["o_update_sender"] = self.update_sender
        signals["o_update_valid"] = self.update_valid
        signals["o_update_round"] = self.update_round
        signals["o_barrier_out"] = self.barrier_out
        signals["i_update_ack"] = self.update_ack
        signals["o_kernel_error"] = self.kernel_error

        self.specials += Instance("{}_apply".format(config.name), **signals)


class NetlistScatterKernelWrapper(Module):
    def __init__(self, config):
        interfaces = import_module("{}.interfaces".format(config.name))

        self.update_in = Record(set_layout_parameters(interfaces.payload_layout, **config.addresslayout.get_params()))
        self.num_neighbors_in = Signal(config.addresslayout.edgeidsize)
        self.neighbor_in = Signal(config.addresslayout.nodeidsize)
        self.sender_in = Signal(config.addresslayout.nodeidsize)
        self.round_in = Signal(config.addresslayout.channel_bits)
        self.barrier_in = Signal()
        self.valid_in = Signal()
        self.ready = Signal()

        self.message_out = Record(set_layout_parameters(interfaces.payload_layout, **config.addresslayout.get_params()))
        self.neighbor_out = Signal(config.addresslayout.nodeidsize)
        self.sender_out = Signal(config.addresslayout.nodeidsize)
        self.round_out = Signal(config.addresslayout.channel_bits)
        self.valid_out = Signal()
        self.message_ack = Signal()
        self.barrier_out = Signal()

        signals = {}
        signals["i_sys_clk"] = ClockSignal()
        # signals["i_sys_rst"] = ResetSignal()

        _add_fields(signals, self.update_in, "i")
        signals["i_num_neighbors_in"] = self.num_neighbors_in
        signals["i_neighbor_in"] = self.neighbor_in
        signals["i_sender_in"] = self.sender_in
        signals["i_round_in"] = self.round_in
        signals["i_barrier_in"] = self.barrier_in
        signals["i_valid_in"] = self.valid_in
        signals["o_ready"] = self.ready

        _add_fields(signals, self.message_out, "o")
        signals["o_neighbor_out"] = self.neighbor_out
        signals["o_sender_out"] = self.sender_out
        signals["o_round_out"] = self.round_out
        signals["o_valid_out"] = self.valid_out
        signals["o_barrier_out"] = self.barrier_out
        signals["i_message_ack"] = self.message_ack

        self.specials += Instance("{}_scatter".format(config.name), **signals)
