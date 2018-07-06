from migen import *
from entangler.core import *



def msm_master_test(dut):
    yield dut.m_end.eq(10)
    yield dut.is_master.eq(1)
    yield dut.time_remaining.eq(100)

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


def msm_standalone_test(dut):
    yield dut.m_end.eq(10)
    yield dut.is_master.eq(1)
    yield dut.standalone.eq(1)
    yield dut.time_remaining_buf.eq(80)

    yield
    yield

    def run_a_while(allow_success=True):
        # Run and check we finish when we get a herald (if allow_success) or
        # that we time out
        for _ in range(20):
            yield
        yield dut.run_stb.eq(1)
        yield
        yield dut.run_stb.eq(0)
        finished = False
        for i in range(100):
            if i == 40 and allow_success:
                yield dut.herald.eq(1)
            if i>40 and (yield dut.done_stb):
                finished = True
            yield
        yield dut.herald.eq(0)
        assert finished
        success = yield dut.success
        assert success == allow_success

    yield from run_a_while()

    # Check core still works with a full reset
    yield from run_a_while()

    # Check timeout works
    yield from run_a_while(False)



def msm_pair_test(dut):
    yield dut.master.m_end.eq(10)
    yield dut.slave.m_end.eq(10)
    yield dut.master.time_remaining.eq(100)
    yield dut.slave.time_remaining.eq(100)

    yield
    yield dut.master.run_stb.eq(1)
    yield
    yield dut.master.run_stb.eq(0)

    for i in range(100):
        if i == 4:
            yield dut.slave.run_stb.eq(1)
        if i == 5:
            yield dut.slave.run_stb.eq(0)
        if i == 9:
            yield dut.master.herald.eq(1)
        yield




if __name__ == "__main__":
    dut = MsmPair()
    run_simulation(dut, msm_pair_test(dut), vcd_name="msm_pair.vcd")

    dut = MainStateMachine()
    run_simulation(dut, msm_standalone_test(dut), vcd_name="msm_standalone.vcd")