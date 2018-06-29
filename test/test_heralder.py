from migen import *
from entangler.core import *

patterns = [0b1001, 0b0110, 0b1010, 0b0101]
n_sig = 4

def heralder_test(dut):
    for i,p in enumerate(patterns):
        yield dut.patterns[i].eq(p)
    yield

    for j in range(2**len(patterns)):
        yield dut.pattern_ens.eq(j)
        yield
        for i in range(2**n_sig):
            yield dut.sig.eq(i)
            yield
            assert (yield dut.herald) == any([p==i and (j & 2**n) for n,p in enumerate(patterns)])

if __name__ == "__main__":
    dut = Heralder(n_sig=n_sig, n_patterns=len(patterns))
    run_simulation(dut, heralder_test(dut), vcd_name="heralder.vcd")