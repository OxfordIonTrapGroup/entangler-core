from migen import *
from entangler.core import *

patterns = [2, 5, 9]
n_sig = 4

def heralder_test(dut):
    for i,p in enumerate(patterns):
        yield dut.patterns[i].eq(p)
    yield

    for i in range(16):
        yield dut.sig.eq(i)
        yield
        assert (yield dut.herald) == any([p==i for p in patterns])

if __name__ == "__main__":
    dut = Heralder(n_sig=n_sig, n_patterns=len(patterns))
    run_simulation(dut, heralder_test(dut), vcd_name="heralder.vcd")