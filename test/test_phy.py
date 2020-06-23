from migen import *
from entangler.driver import *
from entangler.phy import *


def rtio_output_event(rtlink, addr, data):
    yield rtlink.o.address.eq(addr)
    yield rtlink.o.data.eq(data)
    yield rtlink.o.stb.eq(1)
    yield
    yield rtlink.o.stb.eq(0)


def rtio_input(rtlink, timeout):
    for i in range(timeout):
        if (yield rtlink.i.stb):
            break
        yield
    else:
        raise TimeoutError
    return (yield rtlink.i.data)


class MockPhy(Module):
    def __init__(self, counter):
        self.fine_ts = Signal(3)
        self.stb_rising = Signal()
        self.t_event = Signal(32)

        # # #
        self.sync += [
            self.stb_rising.eq(0),
            self.fine_ts.eq(0),
            If(counter == self.t_event[3:],
                self.stb_rising.eq(1),
                self.fine_ts.eq(self.t_event[:3])
            ).Else(
                self.stb_rising.eq(0)
            )
        ]


class PhyHarness(Module):
    def __init__(self):
        self.counter = Signal(32)

        self.submodules.phy_apd0 = MockPhy(self.counter)
        self.submodules.phy_apd1 = MockPhy(self.counter)
        self.submodules.phy_apd2 = MockPhy(self.counter)
        self.submodules.phy_apd3 = MockPhy(self.counter)
        self.submodules.phy_ref = MockPhy(self.counter)
        input_phys = [
            self.phy_apd0, self.phy_apd1, self.phy_apd2, self.phy_apd3, self.phy_ref
        ]

        core_link_pads = None
        output_pads = None
        passthrough_sigs = None
        self.submodules.core = Entangler(core_link_pads,
                                         output_pads,
                                         passthrough_sigs,
                                         input_phys,
                                         simulate=True)

        self.comb += self.counter.eq(self.core.core.msm.m)


def test_basic(dut):
    def out(addr, data):
        yield from rtio_output_event(dut.core.rtlink, addr, data)

    def read(timeout):
        return (yield from rtio_input(dut.core.rtlink, timeout))

    def write_heralds(heralds=None):
        data = 0
        for i, h in enumerate(heralds):
            assert i < 4
            data |= (h & 0xf) << (4 * i)
            data |= 1 << (16 + i)
        yield from out(ADDR_W_HERALD, data)

    t_ref = 800
    t_apd0 = 820
    t_apd1 = 825
    yield dut.phy_ref.t_event.eq(t_ref)
    yield dut.phy_apd0.t_event.eq(t_apd0)
    yield dut.phy_apd1.t_event.eq(t_apd1)

    # Outside the test cycle.
    yield dut.phy_apd2.t_event.eq(10000)
    yield dut.phy_apd3.t_event.eq(10000)

    for _ in range(5):
        yield
    yield from out(ADDR_W_CONFIG, 0b110)  # disable, standalone
    yield from write_heralds([0b0101, 0b1010, 0b1100, 0b0011])
    for i in range(4):
        yield from out(ADDR_W_TIMING_BASE + i, (2 * i + 2) * (1 << 16) | 2 * i + 1)
    for i in [0,1]:
        yield from out(ADDR_W_TIMING_BASE + 4 + i, (30<<16) | 18)
    for i in [2,3]:
        yield from out(ADDR_W_TIMING_BASE + 4 + i, (1000<<16) | 1000)

    yield from out(ADDR_W_TCYCLE, 1000 // 8)

    # Enable, standalone.
    yield from out(ADDR_W_CONFIG, 0b111)

    # Run for 2µs.
    yield from out(ADDR_W_RUN, int(2e3 / 8))

    assert (yield from read(200)) == 0b1000, "Unexpected pattern"
    yield

    yield from out(ADDR_R_STATUS, 0)
    assert (yield from read(2)) & 0x2 != 0, "Core not successful"

    yield from out(ADDR_R_NCYCLES, 0)
    assert (yield from read(2)) == 1, "Wrong number of cycles"

    yield from out(ADDR_R_TIMEREMAINING, 0)
    assert (yield from read(2)) == 114, "Wrong amount of time remaining"

    expected_timestamps = [t_apd0 + 8, t_apd1 + 8, 0, 0, t_ref + 8]
    for i, expected in enumerate(expected_timestamps):
        yield from out(ADDR_R_TIMESTAMP_BASE + i, 0)
        assert (yield from read(2)) == expected
    for i, expected in enumerate([1, 1, 0, 0]):
        yield from out(ADDR_R_COUNTER_RESULT_BASE + i, 0)
        assert (yield from read(2)) == expected
    for _ in range(5):
        yield


def test_timeout(dut):
    """Test that timeout works as the timeout is swept to occur at all possible
    points in the state machine operation"""
    def out(addr, data):
        yield from rtio_output_event(dut.core.rtlink, addr, data)

    def do_timeout(timeout, n_cycles=10):
        yield
        yield from out(ADDR_W_CONFIG, 0b110)  # disable, standalone
        yield from out(ADDR_W_TCYCLE, n_cycles)
        yield from out(ADDR_W_CONFIG, 0b111)  # Enable standalone
        yield from out(ADDR_W_RUN, timeout)

        timedout = False
        for i in range(timeout + n_cycles + 50):
            if (yield dut.core.rtlink.i.stb):
                data = (yield dut.core.rtlink.i.data)
                if data == 0x3fff:
                    # This should be the first and only timeout
                    assert not timedout
                    # Timeout should happen in a timely fashion
                    assert i <= timeout + n_cycles + 5
                    timedout = True
            yield
        assert timedout

    for i in range(1, 20):
        yield from do_timeout(i, n_cycles=10)


if __name__ == "__main__":
    dut = PhyHarness()
    run_simulation(dut,
                   test_basic(dut),
                   vcd_name="phy.vcd",
                   clocks={
                       "sys": 8,
                       "rio": 8,
                       "rio_phy": 8
                   })

    dut = PhyHarness()
    run_simulation(dut,
                   test_timeout(dut),
                   vcd_name="phy_timeout.vcd",
                   clocks={
                       "sys": 8,
                       "rio": 8,
                       "rio_phy": 8
                   })
