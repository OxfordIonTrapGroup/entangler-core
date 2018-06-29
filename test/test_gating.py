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


class GaterHarness(Module):
    def __init__(self):
        self.m = Signal(14)
        self.rst = Signal()
        self.sync += [
            self.m.eq(self.m+1),
            If(self.rst, self.m.eq(0))
        ]

        self.submodules.phy_ref = MockPhy(self.m)
        self.submodules.phy_sig = MockPhy(self.m)

        core = InputGater(self.m, self.phy_ref, self.phy_sig)
        self.submodules.core = core
        self.comb += core.clear.eq(self.rst)



def gater_test(dut, gate_start=None, gate_stop=None, t_ref=None, t_sig=None):
    yield dut.core.gate_start.eq(gate_start)
    yield dut.core.gate_stop.eq(gate_stop)
    yield dut.phy_ref.t_event.eq(t_ref)
    yield dut.phy_sig.t_event.eq(t_sig)
    yield
    yield
    yield dut.rst.eq(1)
    yield
    yield dut.rst.eq(0)

    for _ in range(20):
        yield

    triggered = (yield dut.core.triggered)

    ref_coarse_ts = (yield dut.core.ref_coarse_ts)
    ref_fine_ts = (yield dut.core.ref_fine_ts)
    sig_coarse_ts = (yield dut.core.sig_coarse_ts)
    sig_fine_ts = (yield dut.core.sig_fine_ts)

    print(triggered, ref_coarse_ts, ref_fine_ts, sig_coarse_ts, ref_fine_ts)

    dt = t_sig-t_ref
    expected_triggered = (dt >= gate_start) & (dt <= gate_stop)
    assert(triggered==expected_triggered)


if __name__ == "__main__":
    dut = GaterHarness()
    run_simulation(dut, gater_test(dut, 20,30,20,41), vcd_name="gater.vcd")

    gate_start=8
    gate_stop=25
    t_ref=20

    dut = GaterHarness()
    run_simulation(dut, gater_test(dut, gate_start, gate_stop, t_ref, t_ref+gate_start-1))
    
    dut = GaterHarness()
    run_simulation(dut, gater_test(dut, gate_start, gate_stop, t_ref, t_ref+gate_start))

    dut = GaterHarness()
    run_simulation(dut, gater_test(dut, gate_start, gate_stop, t_ref, t_ref+gate_stop))

    dut = GaterHarness()
    run_simulation(dut, gater_test(dut, gate_start, gate_stop, t_ref, t_ref+gate_stop+1))