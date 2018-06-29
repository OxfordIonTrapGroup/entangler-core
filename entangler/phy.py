from migen import *

from artiq.gateware.rtio import rtlink
from entangler.core import EntanglerCore


class Entangler(Module):
    def __init__(self, if_pads, output_pads, output_sigs, input_phys):
        """
        if_pads: EEM pads for inter-Kasli link
        output_pads: pads for 4 output signals
        output_sigs: signals from output phys, connected to output_pads when
            core not running
        input_phys: serdes phys for 4 inputs
        """
        self.rtlink = rtlink.Interface(
            rtlink.OInterface(
                data_width=32,
                address_width=5,
                enable_replace=False),
            rtlink.IInterface(
                data_width=14,
                timestamped=False)
            )

        # # #

        self.submodules.core = EntanglerCore(if_pads, output_pads, output_sigs,
                        input_phys)



        read_en = self.rtlink.o.address[4]
        write_timings = Signal()
        self.comb += [
            self.rtlink.o.busy.eq(0),
            write_timings.eq(self.rtlink.o.address[4:3] == 1),
        ]


        output_t_starts = [seq.m_start for seq in self.core.sequencers]
        output_t_ends = [seq.m_stop for seq in self.core.sequencers]
        output_t_starts += [gater.gate_start
                                for gaters in self.apd_gaters
                                for gater in gaters]
        output_t_ends += [gater.gate_end
                                for gaters in self.apd_gaters
                                for gater in gaters]

        self.sync.rio += [
            self.core.msm.run_stb.eq(0),
            If(write_timings & self.rtlink.o.stb, 
                    output_t_starts[self.rtlink.o.address[2:]].eq(self.rtlink.o.data[13:]),
                    output_t_ends[self.rtlink.o.address[2:]].eq(self.rtlink.o.data[29:16])
                ),
            If(self.rtlink.o.address==0 & self.rtlink.o.stb,
                    # Write config
                    self.core.enable.eq(self.rtlink.o.data[0]),
                    self.core.msm.is_master.eq(self.rtlink.o.data[1]),
                    self.core.msm.standalone.eq(self.rtlink.o.data[2]),
                ),
            If(self.rtlink.o.address==1 & self.rtlink.o.stb,
                    # Write timeout counter and start core running
                    self.core.msm.time_remaining.eq(self.rtlink.o.data),
                    self.core.msm.run_stb.eq(1)
                ),
            If(self.rtlink.o.address==2 & self.rtlink.o.stb,
                    # Write cycle length
                    self.core.msm.m_end.eq(self.rtlink.o.data[:10])
                ),
            If(self.rtlink.o.address==3 & self.rtlink.o.stb,
                    # Write herald patterns and enables
                    *[self.core.heralder.patterns[i].eq(self.rtlink.o.data[4*i:4*(i+1)]) for i in range(4)],
                    self.core.heralder.pattern_ens.eq(self.rtlink.o.data[16:20])
                ),
        ]


        read = Signal()
        read_timings = Signal()
        read_addr = Signal()

        # Input timestamps are [ref, apd1_1, apd1_2, apd2_1, apd2_2]
        input_timestamps = self.apd_gaters[0][0].t_ref
        input_timestamps += [gater.t_sig
                                for gaters in self.apd_gaters
                                for gater in gaters]

        self.sync.rio += [
                If(read,
                    read.eq(0)
                ),
                If(self.rtlink.o.stb,
                    read.eq(read_en),
                    read_timings.eq(self.rtlink.o.address[4:3] == 3),
                    read_addr.eq(self.rtlink.o.address[2:]),
                )
        ]

        n_cycles = self.core.msm.cycles_completed 
        status = Signal(2)
        self.comb += status.eq(Cat(self.core.msm.ready,
                                   self.core.msm.success,
                                   self.core.msm.timeout))

        # Generate an input event if we have a read request RTIO Output event, 
        # Or if the core has finished.
        # If the core is finished output the herald match or 0x3fff on timeout
        # We expect to never get a read request and a core finished event at the same time
        self.comb += [
                self.rtlink.i.stb.eq(read | self.core.done_stb),
                self.rtlink.i.data.eq(
                    Mux(self.core.done_stb, self.core.heralder.matches if self.core.success else 0x3fff,
                        Mux(read_timings,
                            input_timestamps[read_addr],
                            status if read_addr==0 else n_cycles)))
        ]