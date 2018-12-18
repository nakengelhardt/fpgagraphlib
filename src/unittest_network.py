import unittest
import random
import logging

from migen import *
from migen.genlib.record import *

from tbsupport import *
from core_init import resolve_defaults
from configparser import ConfigParser

from fifo_network import Network, MultiNetwork

def get_generators(self, num_rounds):
    sent = [[] for _ in range(self.tb.config.addresslayout.num_pe)]
    received = [[] for _ in range(self.tb.config.addresslayout.num_pe)]
    num_sent = [[0 for _ in range(self.tb.config.addresslayout.num_pe)] for _ in range(self.tb.config.addresslayout.num_pe)]
    for node in self.tb.graph:
        for neighbor in self.tb.graph[node]:
            sender_pe = self.tb.config.addresslayout.pe_adr(node)
            dest_pe = self.tb.config.addresslayout.pe_adr(neighbor)
            msg = {"dest_id": neighbor, "sender": node, "payload": 0, "barrier":0, "dest_pe": dest_pe}
            sent[sender_pe].append(msg)
            num_sent[sender_pe][dest_pe] += 1
            received[dest_pe].append(msg)

    # print("Messages to send:")
    # for pe in range(self.tb.config.addresslayout.num_pe):
    #     print("PE {}: {}".format(pe, sent[pe]))

    def gen_input(pe, num_rounds):
        fpga = pe // self.tb.config.addresslayout.num_pe_per_fpga
        local_pe = pe % self.tb.config.addresslayout.num_pe_per_fpga
        network_interface = self.tb.dut[fpga].network_interface[local_pe]
        for roundpar in range(num_rounds):
            messages = sent[pe].copy()
            while messages:
                msg = messages.pop(random.randrange(len(messages)))
                yield (network_interface.msg.dest_id.eq(msg["dest_id"]))
                yield (network_interface.msg.sender.eq(msg["sender"]))
                yield (network_interface.msg.payload.eq(msg["payload"]))
                yield (network_interface.msg.barrier.eq(msg["barrier"]))
                yield (network_interface.msg.roundpar.eq(roundpar))
                yield (network_interface.dest_pe.eq(msg["dest_pe"]))
                yield (network_interface.valid.eq(random.choice([0,1])))
                yield
                while not ((yield network_interface.valid) and (yield network_interface.ack)):
                    yield (network_interface.valid.eq(1)) #random.choice([0,1])
                    yield
            messages = [{"dest_id": num_sent[pe][i], "sender": pe << log2_int(self.tb.config.addresslayout.num_nodes_per_pe), "payload": 0, "barrier": 1, "dest_pe": i} for i in range(self.tb.config.addresslayout.num_pe)]
            while messages:
                msg = messages.pop(random.randrange(len(messages)))
                yield (network_interface.msg.dest_id.eq(msg["dest_id"]))
                yield (network_interface.msg.sender.eq(msg["sender"]))
                yield (network_interface.msg.payload.eq(msg["payload"]))
                yield (network_interface.msg.barrier.eq(msg["barrier"]))
                yield (network_interface.msg.roundpar.eq(roundpar))
                yield (network_interface.dest_pe.eq(msg["dest_pe"]))
                yield (network_interface.valid.eq(random.choice([0,1])))
                yield
                while not ((yield network_interface.valid) and (yield network_interface.ack)):
                    yield (network_interface.valid.eq(1)) #random.choice([0,1])
                    yield
        yield (network_interface.valid.eq(0))
        yield

    def gen_output(pe, num_rounds):
        fpga = pe // self.tb.config.addresslayout.num_pe_per_fpga
        local_pe = pe % self.tb.config.addresslayout.num_pe_per_fpga
        apply_interface = self.tb.dut[fpga].apply_interface[local_pe]
        logger = logging.getLogger('gen_output')
        for roundpar in range(num_rounds):
            messages = received[pe].copy()
            logger.info("PE {} entering round {}.".format(pe, roundpar))
            logger.debug("Messages expected: {}".format(messages))
            while messages:
                yield (apply_interface.ack.eq(random.choice([0,1])))
                if (yield apply_interface.valid) and (yield apply_interface.ack):
                    dest_id = yield apply_interface.msg.dest_id
                    sender = yield apply_interface.msg.sender
                    payload = yield apply_interface.msg.payload
                    barrier = yield apply_interface.msg.barrier
                    rnd = yield apply_interface.msg.roundpar
                    logger.debug("PE {} received message ({} -> {})".format(pe, sender, dest_id))
                    self.assertFalse(barrier)
                    self.assertEqual(rnd, roundpar)
                    for msg in messages:
                        if (msg["dest_id"] == dest_id) and (msg["sender"] == sender):
                            messages.remove(msg)
                            break
                    else:
                        self.fail("PE {} received message it wasn't supposed to: {} -> {} (dest_pe={})".format(pe, sender, dest_id, self.tb.config.addresslayout.pe_adr(dest_id)))
                yield
            logger.info("PE {} received all messages of round {}".format(pe, roundpar))

            while True:
                yield (apply_interface.ack.eq(random.choice([0,1])))
                if (yield apply_interface.valid) and (yield apply_interface.ack):
                    dest_id = yield apply_interface.msg.dest_id
                    sender = yield apply_interface.msg.sender
                    payload = yield apply_interface.msg.payload
                    barrier = yield apply_interface.msg.barrier
                    rnd = yield apply_interface.msg.roundpar
                    logger.debug("PE {} received barrier (round {})".format(pe, rnd))
                    self.assertTrue(barrier)
                    self.assertEqual(rnd, roundpar, "PE {} expected round {} but received round {}".format(pe, roundpar, rnd))
                    break
                yield
            yield
        yield (apply_interface.ack.eq(0))

    @passive
    def gen_timeout(cycles):
        time = 0
        while time < cycles:
            yield
            time += 1
        self.fail("Timeout")

    return [gen_input(i,num_rounds) for i in range(self.tb.config.addresslayout.num_pe)] + [gen_output(i,num_rounds) for i in range(self.tb.config.addresslayout.num_pe)] + [gen_timeout(500*num_rounds)]

class NetworkCase(SimCase, unittest.TestCase):
    class TestBench(Module):
        def __init__(self):
            configparser = ConfigParser()
            configparser['arch'] = {'num_pe' : 8}
            configparser['graph'] = {}
            configparser['app'] = {'algo': "bfs"}
            configparser['logging'] = {'log_file_name': "unittest_network", 'disable_logfile': False}

            self.config = resolve_defaults(configparser, num_nodes=32, num_edges=32*4)
            self.graph = self.config.adj_dict

            self.submodules.dut = [Network(self.config)]

    def test_network(self):
        num_rounds = 3
        self.run_with(get_generators(self, num_rounds), vcd_name="unittest_network.vcd")


class MultiNetworkCase(SimCase, unittest.TestCase):
    class TestBench(Module):
        def __init__(self):
            configparser = ConfigParser()
            configparser['arch'] = {'num_pe': 4, 'num_fpga': 2}
            configparser['graph'] = {}
            configparser['app'] = {'algo': "bfs"}
            configparser['logging'] = {'log_file_name': "unittest_network", 'disable_logfile': False}

            self.config = resolve_defaults(configparser, num_nodes=32, num_edges=32*4)
            self.graph = self.config.adj_dict

            self.submodules.dut = [MultiNetwork(self.config, fpga_id=i) for i in range(self.config.addresslayout.num_fpga)]

            # inter-core communication
            for i in range(self.config.addresslayout.num_fpga):
                core_idx = 0
                for j in range(self.config.addresslayout.num_fpga - 1):
                    if i == j:
                        core_idx += 1
                    if j < i:
                        if_idx = i - 1
                    else:
                        if_idx = i
                    # print("Connecting core {} out {} to core {} in {}".format(i, j, core_idx, if_idx))
                    self.comb += self.dut[i].external_network_interface_out[j].connect(self.dut[core_idx].external_network_interface_in[if_idx])
                    core_idx += 1

    def test_network(self):
        num_rounds = 3
        self.run_with(get_generators(self, num_rounds), vcd_name="test_network.vcd")

if __name__ == "__main__":
    random.seed(42)
    unittest.main()
