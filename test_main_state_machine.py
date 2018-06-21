from migen import *
from core import *



def msm_master_test(dut):
    yield dut.m_end.eq(10)
    yield dut.is_master.eq(1)
    yield dut.cycles_remaining.eq(3)

    for i in range(30):
        if i == 5:
            yield dut.slave_ready.eq(1)
        yield

def msm_slave_test(dut):
    yield dut.m_end.eq(10)
    yield dut.is_master.eq(1)
    yield dut.cycles_remaining.eq(3)

    for i in range(30):
        if i == 5:
            yield dut.slave_ready.eq(1)
        yield


class MsmPair(Module):
    def __init__(self):
        self.submodules.master = MainStateMachine()
        self.submodules.slave = MainStateMachine()

        self.comb += [
            self.master.is_master.eq(1),
            self.master.slave_ready.eq(self.slave.ready),
            self.slave.trigger_in.eq(self.master.trigger_out),
            self.slave.success_in.eq(self.master.success)
        ]


def msm_pair_test(dut):
    yield dut.master.m_end.eq(10)
    yield dut.slave.m_end.eq(10)
    yield dut.master.cycles_remaining.eq(4)
    yield dut.slave.cycles_remaining.eq(4)

    yield
    yield dut.master.run.eq(1)

    for i in range(100):
        if i == 4:
            yield dut.slave.run.eq(1)
        if i == 50:
            yield dut.master.herald.eq(1)
        yield

if __name__ == "__main__":
    dut = MsmPair()
    run_simulation(dut, msm_pair_test(dut), vcd_name="msm.vcd")