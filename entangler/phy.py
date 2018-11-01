from migen import *

from artiq.gateware.rtio import rtlink
from entangler.core import EntanglerCore


class Entangler(Module):
    def __init__(self, core_link_pads, output_pads, output_sigs, input_phys, simulate=False):
        """
        core_link_pads: EEM pads for inter-Kasli link
        output_pads: pads for 4 output signals (422sigma, 1092, 422 ps trigger, aux)
        output_sigs: signals from output phys, connected to output_pads when core not
            running
        input_phys: serdes phys for 5 inputs – APD0-3 and 422ps trigger in
        """
        self.rtlink = rtlink.Interface(
            rtlink.OInterface(
                data_width=32,
                address_width=5,
                enable_replace=False),
            rtlink.IInterface(
                data_width=14,
                timestamped=True)
            )

        # # #

        self.submodules.core = ClockDomainsRenamer("rio")(
                    EntanglerCore(core_link_pads, output_pads, output_sigs,
                        input_phys, simulate=simulate))

        read_en = self.rtlink.o.address[4]
        write_timings = Signal()
        self.comb += [
            self.rtlink.o.busy.eq(0),
            write_timings.eq(self.rtlink.o.address[3:5] == 1),
        ]

        output_t_starts = [seq.m_start for seq in self.core.sequencers]
        output_t_ends = [seq.m_stop for seq in self.core.sequencers]
        output_t_starts += [gater.gate_start
                                for gater in self.core.apd_gaters]
        output_t_ends += [gater.gate_stop
                                for gater in self.core.apd_gaters]
        cases = {}
        for i in range(len(output_t_starts)):
            cases[i] = [output_t_starts[i].eq(self.rtlink.o.data[:16]),
                        output_t_ends[i].eq(self.rtlink.o.data[16:])]

        # Write timeout counter and start core running
        self.comb += [
            self.core.msm.time_remaining_buf.eq(self.rtlink.o.data),
            self.core.msm.run_stb.eq( (self.rtlink.o.address==1) & self.rtlink.o.stb )
        ]

        self.sync.rio += [
            If(write_timings & self.rtlink.o.stb,
                    Case(self.rtlink.o.address[:3], cases)
                ),
            If( (self.rtlink.o.address==0) & self.rtlink.o.stb,
                    # Write config
                    self.core.enable.eq(self.rtlink.o.data[0]),
                    self.core.msm.is_master.eq(self.rtlink.o.data[1]),
                    self.core.msm.standalone.eq(self.rtlink.o.data[2]),
                ),
            If( (self.rtlink.o.address==2) & self.rtlink.o.stb,
                    # Write cycle length
                    self.core.msm.m_end.eq(self.rtlink.o.data[:10])
                ),
            If( (self.rtlink.o.address==3) & self.rtlink.o.stb,
                    # Write herald patterns and enables
                    *[self.core.heralder.patterns[i].eq(self.rtlink.o.data[4*i:4*(i+1)]) for i in range(4)],
                    self.core.heralder.pattern_ens.eq(self.rtlink.o.data[16:20])
                ),
        ]


        read = Signal()
        read_timings = Signal()
        read_addr = Signal(3)

        # Input timestamps are [apd0, apd1, apd2, apd3, ref]
        input_timestamps = [gater.sig_ts for gater in self.core.apd_gaters]
        input_timestamps.append(self.core.apd_gaters[0].ref_ts)
        cases = {}
        timing_data = Signal(14)
        for i, ts in enumerate(input_timestamps):
            cases[i] = [timing_data.eq(ts)]
        self.comb += Case(read_addr, cases)


        self.sync.rio += [
                If(read,
                    read.eq(0)
                ),
                If(self.rtlink.o.stb,
                    read.eq(read_en),
                    read_timings.eq(self.rtlink.o.address[3:5] == 0b11),
                    read_addr.eq(self.rtlink.o.address[:3]),
                )
        ]

        status = Signal(3)
        self.comb += status.eq(Cat(self.core.msm.ready,
                                   self.core.msm.success,
                                   self.core.msm.timeout))

        reg_read = Signal(14)
        cases = {}
        cases[0] = [reg_read.eq(status)]
        cases[1] = [reg_read.eq(self.core.msm.cycles_completed)]
        cases[2] = [reg_read.eq(self.core.msm.time_remaining)]
        cases[3] = [reg_read.eq(self.core.triggers_received)]
        self.comb += Case(read_addr, cases)

        # Generate an input event if we have a read request RTIO Output event, 
        # Or if the core has finished.
        # If the core is finished output the herald match or 0x3fff on timeout
        # We expect to never get a read request and a core finished event at the same time
        self.comb += [
                self.rtlink.i.stb.eq(read | (self.core.enable & self.core.msm.done_stb)),
                self.rtlink.i.data.eq(
                    Mux(self.core.enable & self.core.msm.done_stb, Mux(self.core.msm.success,self.core.heralder.matches, 0x3fff),
                        Mux(read_timings,
                            timing_data,
                            reg_read)
                        )
                    )
        ]