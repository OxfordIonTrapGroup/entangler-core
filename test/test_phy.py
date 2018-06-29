from migen import *
from entangler.phy import *


def rtio_output_event(rtlink, addr, data):
    yield rtlink.o.address.eq(addr)
    yield rtlink.o.data.eq(data)
    yield rtlink.o.stb.eq(1)
    yield
    yield rtlink.o.stb.eq(0)


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


class PhyHarness(Module):
    def __init__(self):
        self.counter = Signal(32)

        self.submodules.phy_ref = MockPhy(self.counter)
        self.submodules.phy_1 = MockPhy(self.counter)
        self.submodules.phy_2 = MockPhy(self.counter)
        input_phys = [self.phy_ref, self.phy_1, self.phy_2]

        if_pads = None
        output_pads = None
        output_sigs = None
        self.submodules.core = Entangler(if_pads, output_pads, output_sigs, input_phys, simulate=True)

        self.comb += self.counter.eq(self.core.core.msm.m)


def test(dut):
    def out(addr, data):
        yield from rtio_output_event(dut.core.rtlink, addr, data)

    for _ in range(5):
        yield
    yield from out(0b00, 0b110)
    yield from out(0b10, 30)
    for _ in range(5):
        yield


if __name__ == "__main__":
    dut = PhyHarness()
    run_simulation(dut, test(dut), vcd_name="phy.vcd",  clocks={"sys": 8, "rio":8})
