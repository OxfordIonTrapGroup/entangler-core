from migen import *

counter_width = 10


class ChannelSequencer(Module):
    def __init__(self, m):
        self.m_start = Signal(counter_width)
        self.m_stop = Signal(counter_width)
        self.clear = Signal()

        self.stb_start = Signal()
        self.stb_stop = Signal()

        self.output = Signal()

        ###

        self.comb += [
            self.stb_start.eq(m == self.m_start),
            self.stb_stop.eq(m == self.m_stop)
        ]

        self.sync += [
            If(self.stb_start,
                self.output.eq(1)
            ).Else(
                If(self.stb_stop,
                    self.output.eq(0))
            ),
            If(self.clear, self.output.eq(0))
        ]


class InputGater(Module):
    """Event gater that connects to ttl_serdes_generic phys.

    The gate is defined as a time window after a reference event occurs.
    The reference time is that of a rising edge on phy_ref. There is no protection against multiple edges on phy_ref.
    The gate start and stop are specified as offsets in mu (=1ns mostly) from this reference event.

    The module is triggered after it has seen a reference event, then subsequently a signal edge in the gate window.
    Once the module is triggered subsequent signal edges are ignored.
    Clear has to be asserted to clear the reference edge and the triggered flag.

    The start gate offset must be at least 8mu.
    """
    def __init__(self, m, phy_ref, phy_sig):
        self.clear = Signal()

        self.triggered = Signal()

        n_fine = len(phy_ref.fine_ts)

        self.ref_coarse_ts = Signal(counter_width)
        self.ref_fine_ts = Signal(n_fine)

        self.sig_coarse_ts = Signal(counter_width)
        self.sig_fine_ts = Signal(n_fine)

        # In mu
        self.gate_start = Signal(14)
        self.gate_stop = Signal(14)

        # # #

        got_ref = Signal()

        # Absolute gate times, calculated when we get the reference event
        abs_gate_start = Signal(counter_width+n_fine)
        abs_gate_stop = Signal(counter_width+n_fine)

        t_ref = Signal(counter_width+n_fine)
        self.comb += t_ref.eq(Cat(phy_ref.fine_ts,m))

        self.sync += [
            If(phy_ref.stb_rising,
                got_ref.eq(1),
                self.ref_coarse_ts.eq(m),
                self.ref_fine_ts.eq(phy_ref.fine_ts),
                abs_gate_start.eq(self.gate_start + t_ref),
                abs_gate_stop.eq(self.gate_stop + t_ref)
            ),
            If(self.clear,
                got_ref.eq(0),
                self.triggered.eq(0)
            )
        ]

        past_window_start = Signal()
        before_window_end = Signal()
        triggering = Signal()
        t_sig = Signal(counter_width+n_fine)
        self.comb += [
            t_sig.eq(Cat(phy_sig.fine_ts,m)),
            past_window_start.eq(t_sig >= abs_gate_start),
            before_window_end.eq(t_sig <= abs_gate_stop),
            triggering.eq(past_window_start & before_window_end)
        ]

        self.sync += [
            If(phy_sig.stb_rising & ~self.triggered,
                self.triggered.eq(triggering),
                self.sig_coarse_ts.eq(m),
                self.sig_fine_ts.eq(phy_sig.fine_ts)
            )
        ]


class Heralder(Module):
    """Asserts 'herald' if input vector matches any pattern in patterns"""
    def __init__(self, n_sig = 4, n_patterns=1):
        self.sig = Signal(n_sig)
        self.patterns = [Signal(n_sig) for _ in range(n_patterns)]
        self.pattern_ens = Signal(n_patterns)
        self.matches = Signal(n_patterns)

        self.herald = Signal()

        # # #

        self.comb += [self.matches[i].eq(p==self.sig) for i, p in enumerate(self.patterns)]
        self.comb += self.herald.eq( self.pattern_ens & self.matches != 0 )


class MainStateMachine(Module):
    def __init__(self, counter_width=10):
        self.m = Signal(counter_width)
        self.time_remaining = Signal(32) # Clock cycles remaining before timeout
        self.cycles_completed = Signal(14) # How many iterations of the loop have completed since last start

        self.run_stb = Signal() # Pulsed to start core running until timeout or success
        self.done_stb = Signal() # Pulsed when core has finished (on timeout or success)

        self.timeout = Signal()
        self.success = Signal()

        self.ready = Signal()

        self.herald = Signal()

        self.is_master = Signal()

        self.trigger_out = Signal() # Trigger to slave
        self.trigger_in = Signal() # Trigger from master
        self.success_in = Signal()

        self.slave_ready = Signal()

        self.m_end = Signal(counter_width) # Number of clock cycles to run main loop for

        ###

        self.comb += self.timeout.eq(self.time_remaining == 0)
        self.sync += If(~self.timeout, self.time_remaining.eq(self.time_remaining-1))

        # Ready asserted when run_stb is pulsed, and cleared on success or timeout
        self.sync += [
            self.done_stb.eq(0),
            If(self.run_stb, self.ready.eq(1), self.cycles_completed.eq(0), self.success.eq(0)),
            If(self.timeout | self.success, self.ready.eq(0), self.done_stb.eq(1))
        ]

        fsm = FSM()
        self.submodules += fsm

        fsm.act("IDLE",
            If(self.is_master,
                If(self.slave_ready & self.ready, NextState("TRIGGER_SLAVE"))
            ).Else(
                If(self.ready & self.trigger_in, NextState("COUNTER"))
            ),
            NextValue(self.m, 0),
            self.trigger_out.eq(0)
        )
        fsm.act("TRIGGER_SLAVE",
            NextState("TRIGGER_SLAVE2"),
            self.trigger_out.eq(1)
        )
        fsm.act("TRIGGER_SLAVE2",
            NextState("COUNTER"),
            self.trigger_out.eq(1)
        )
        fsm.act("COUNTER",
            NextValue(self.m, self.m + 1),
            If(self.m == self.m_end,
                NextValue(self.cycles_completed, self.cycles_completed+1),
                If(self.is_master, 
                    If(self.herald, NextValue(self.success, 1)),
                    NextState("IDLE")
                ).Else(
                    NextState("SLAVE_SUCCESS_WAIT")
                )
            ),
            self.trigger_out.eq(0)
        )
        fsm.act("SLAVE_SUCCESS_WAIT",
            NextState("SLAVE_SUCCESS_CHECK"))
        fsm.act("SLAVE_SUCCESS_CHECK", # On slave, checking if master broadcast success
            If(self.success_in, NextValue(self.success, 1)),
            NextState("IDLE")
        )





class EntanglerCore(Module):
    def __init__(self, if_pads, output_pads, output_sigs, input_phys):
        phy_apd1 = input_phys[0]
        phy_apd2 = input_phys[1]
        phy_422pulse = input_phys[2]

        enable = Signal()
        is_master = Signal()

        # Connect output pads to sequencer output when enabled, otherwise use
        # the RTIO phy output
        sequencer_outputs = [Signal() for _ in range(4)]
        for i in range(4):
            pad = output_pads[i]
            self.specials += Instance("OBUFDS",
                          i_I=sequence_outputs[i] if enable else output_sigs[i],
                          o_O=pad.p, o_OB=pad.n)

        def ts_buf(pad, sig_o, sig_i, en_out):
            # diff. IO.
            # sig_o: output from FPGA
            # sig_i: intput to FPGA
            # en_out: enable FPGA output driver
            self.specials += Instance("IOBUFDS_INTERMDISABLE",
                p_DIFF_TERM="TRUE",
                p_IBUF_LOW_PWR="TRUE",
                p_USE_IBUFDISABLE="TRUE",
                i_IBUFDISABLE=en_out,
                i_INTERMDISABLE=en_out,
                i_I=sig_o, o_O=sig_i, i_T=~en_out,
                io_IO=pad.p, io_IOB=pad.n)

        # Interface between master and slave core
        ts_buf(output_pads[0],
            self.msm.ready, self.msm.slave_ready,
            ~is_master)
        ts_buf(output_pads[1],
            self.msm.trigger_out, self.msm.trigger_in,
            is_master)
        ts_buf(output_pads[2],
            self.msm.success, self.msm.success_in,
            is_master)




        self.submodules.msm = MainStateMachine()

        self.submodules._422sigma_seq = ChannelSequencer()
        self.submodules._1092_seq = ChannelSequencer()
        self.submodules._422pulsed_seq = ChannelSequencer()

        self.submodules.apd_1_seqs = [ChannelSequencer() for _ in range(2)]
        self.submodules.apd_2_seqs = [ChannelSequencer() for _ in range(2)]

        self.submodules.apd_1_gates = [InputGater(phy_apds[0]) for _ in range(2)]
        self.submodules.apd_2_gates = [InputGater(phy_apds[1]) for _ in range(2)]

        self.submodules.heralder = Heralder()

        self.apd_sig = Signal(4)

        for s,g in zip(self.apd_1_seqs, self.apd_1_gates):
            self.comb += g.gate.eq(s.output)
        for s,g in zip(self.apd_2_seqs, self.apd_2_gates):
            self.comb += g.gate.eq(s.output)

        self.comb += [
            self.apd_sig.eq(Cat(self.apd_1_gates[0].triggered,
                                self.apd_1_gates[1].triggered,
                                self.apd_2_gates[0].triggered,
                                self.apd_2_gates[1].triggered)),
            self.heralder.sig.eq(self.apd_sig),
            # self.msm.
        ]




