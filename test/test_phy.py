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

        self.submodules.phy_apd0 = MockPhy(self.counter)
        self.submodules.phy_apd1 = MockPhy(self.counter)
        self.submodules.phy_apd2 = MockPhy(self.counter)
        self.submodules.phy_apd3 = MockPhy(self.counter)
        self.submodules.phy_ref = MockPhy(self.counter)
        input_phys = [self.phy_apd0, self.phy_apd1, self.phy_apd2, self.phy_apd3, self.phy_ref]

        core_link_pads = None
        output_pads = None
        passthrough_sigs = None
        self.submodules.core = Entangler(core_link_pads, output_pads, passthrough_sigs, input_phys, simulate=True)

        self.comb += self.counter.eq(self.core.core.msm.m)


ADDR_CONFIG = 0
ADDR_RUN = 1
ADDR_NCYCLES = 2
ADDR_HERALDS = 3
ADDR_TIMING = 0b1000

def test_basic(dut):
    def out(addr, data):
        yield from rtio_output_event(dut.core.rtlink, addr, data)
    def write_heralds(heralds = None):
        data = 0
        for i, h in enumerate(heralds):
            assert i < 4
            data |= (1<<i) << (4*4)
            data |= h << (4*i)
        yield from out(ADDR_HERALDS, data)

    yield dut.phy_ref.t_event.eq( 1000 )
    yield dut.phy_apd0.t_event.eq( 1000 )
    yield dut.phy_apd1.t_event.eq( 1000 )

    for _ in range(5):
        yield
    yield from out(ADDR_CONFIG, 0b110) # disable, standalone
    yield from write_heralds([0b0101, 0b1010, 0b1100, 0b0101])
    for i in range(4):
        yield from out(ADDR_TIMING+i, (2*i+2)*(1<<16) | 2*i+1)
    # for i in [0,2]:
    #     yield from out(ADDR_TIMING+4+i, (30<<16) | 18)
    # for i in [1,3]:
    #     yield from out(ADDR_TIMING+4+i, (1000<<16) | 1000)
    yield from out(ADDR_NCYCLES, 30)
    yield from out(ADDR_CONFIG, 0b111) # Enable standalone
    yield from out(ADDR_RUN, int(2e3/8))

    for i in range(1000):
        # if i==200:
        #     yield dut.phy_ref.t_event.eq( 8*10+3 )
        #     yield dut.phy_apd0.t_event.eq( 8*10+3 + 18)
        #     yield dut.phy_apd1.t_event.eq( 8*10+3 + 30)
        yield

    yield from out(0b10000, 0) # Read status
    yield
    yield from out(0b10000+1, 0) # Read n_cycles
    yield
    yield from out(0b10000+2, 0) # Read time elapsed
    yield
    for i in range(5):
        yield from out(0b11000+i, 0) # Read input timestamps
        yield
    for _ in range(5):
        yield


def test_timeout(dut):
    """Test that timeout works as the timeout is swept to occur at all possible
    points in the state machine operation"""

    def out(addr, data):
        yield from rtio_output_event(dut.core.rtlink, addr, data)

    def do_timeout(timeout, n_cycles = 10):
        yield
        yield from out(ADDR_CONFIG, 0b110) # disable, standalone
        yield from out(ADDR_NCYCLES, n_cycles)
        yield from out(ADDR_CONFIG, 0b111) # Enable standalone
        yield from out(ADDR_RUN, timeout)

        timedout=False
        for i in range(timeout+n_cycles+50):
            if (yield dut.core.rtlink.i.stb):
                data = (yield dut.core.rtlink.i.data)
                if data==0x3fff:
                    # This should be the first and only timeout
                    assert not timedout
                    # Timeout should happen in a timely fashion
                    assert i <= timeout+n_cycles+5
                    timedout=True
            yield
        assert timedout

    for i in range(1,20):
        yield from do_timeout(i,n_cycles=10)


if __name__ == "__main__":
    dut = PhyHarness()
    run_simulation(dut, test_basic(dut), vcd_name="phy.vcd",  clocks={"sys": 8, "rio":8})

    dut = PhyHarness()
    run_simulation(dut, test_timeout(dut), vcd_name="phy_timeout.vcd",  clocks={"sys": 8, "rio":8})
