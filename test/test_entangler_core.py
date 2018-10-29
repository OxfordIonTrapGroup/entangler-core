from migen import *
from entangler.core import *


class MockPhy(Module):
    def __init__(self, counter):
        self.fine_ts = Signal(3)
        self.stb_rising = Signal()
        self.t_event = Signal(32)

        # # #
        self.sync += [
            self.stb_rising.eq(0),
            self.fine_ts.eq(0),
            If(counter==self.t_event[3:],
                self.stb_rising.eq(1),
                self.fine_ts.eq(self.t_event[:3])
            )
        ]


class StandaloneHarness(Module):
    def __init__(self):
        self.counter = Signal(32)

        self.submodules.phy_ref = MockPhy(self.counter)
        self.submodules.phy_1 = MockPhy(self.counter)
        self.submodules.phy_2 = MockPhy(self.counter)
        input_phys = [self.phy_ref, self.phy_1, self.phy_2]

        core_link_pads = None
        output_pads = None
        output_sigs = None
        self.submodules.core = EntanglerCore(core_link_pads, output_pads, output_sigs, input_phys, simulate=True)

        self.comb += self.counter.eq(self.core.msm.m)


def standalone_test(dut):
    yield dut.core.msm.m_end.eq(20)
    yield dut.core.msm.is_master.eq(1)
    yield dut.core.msm.standalone.eq(1)
    yield dut.core.msm.time_remaining.eq(100)

    yield dut.core.sequencers[0].m_start.eq(1)
    yield dut.core.sequencers[0].m_stop.eq(9)
    yield dut.core.sequencers[1].m_start.eq(2)
    yield dut.core.sequencers[1].m_stop.eq(5)
    yield dut.core.sequencers[2].m_start.eq(3)
    yield dut.core.sequencers[2].m_stop.eq(4)
    yield dut.core.sequencers[3].m_start.eq(0)
    yield dut.core.sequencers[3].m_stop.eq(0)

    yield dut.core.apd_gaters[0][0].gate_start.eq(18)
    yield dut.core.apd_gaters[0][0].gate_stop.eq(30)
    yield dut.core.apd_gaters[1][0].gate_start.eq(18)
    yield dut.core.apd_gaters[1][0].gate_stop.eq(30)

    yield dut.phy_ref.t_event.eq( 1000 )
    yield dut.phy_1.t_event.eq( 1000 )
    yield dut.phy_2.t_event.eq( 1000 )

    yield dut.core.heralder.patterns[0].eq(0b0101)
    yield dut.core.heralder.pattern_ens[0].eq(1)

    for _ in range(5):
        yield
    yield dut.core.msm.run_stb.eq(1)
    yield
    yield dut.core.msm.run_stb.eq(0)

    for i in range(50):
        yield

    yield dut.phy_ref.t_event.eq( 8*10+3 )
    yield dut.phy_1.t_event.eq( 8*10+3 + 18)
    yield dut.phy_2.t_event.eq( 8*10+3 + 30)

    for i in range(50):
        yield

if __name__ == "__main__":
    dut = StandaloneHarness()
    run_simulation(dut, standalone_test(dut), vcd_name="core_standalone.vcd",  clocks={"sys": 8})
