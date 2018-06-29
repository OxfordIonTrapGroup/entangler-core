from migen import *
from entangler.core import *

def channel_sequencer_test(dut):
    yield dut.clear.eq(1)
    yield dut.m_start.eq(10)
    yield dut.m_stop.eq(30)
    yield
    yield dut.clear.eq(0)

    for i in range(100):
        yield dut.m.eq(i)
        yield

        if i==10:
            assert (yield dut.stb_start) == 1
            assert (yield dut.output) == 0
        if i==11:
            assert (yield dut.output) == 1
        if i==30:
            assert (yield dut.stb_stop) == 1
            assert (yield dut.output) == 1
        if i==31:
            assert (yield dut.output) == 0

if __name__ == "__main__":
    dut = ChannelSequencer()
    run_simulation(dut, channel_sequencer_test(dut), vcd_name="sequencer.vcd")