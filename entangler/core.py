from migen import *

# Width of sequence duration counters and the coarse part of input timestamps
# (units of clock cycles).
counter_width = 11


class ChannelSequencer(Module):
    """Pulses `output` between the given edge times.

    `m_start`/`m_stop` specify the values of the given counter signal `m` (assumed to be
    monotonically increasing) between which the output is active. `clear` deasserts the
    output irrespective of the configured times.
    """
    def __init__(self, m):
        self.m_start = Signal(counter_width)
        self.m_stop = Signal(counter_width)
        self.clear = Signal()

        self.output = Signal()

        # # #

        self.stb_start = Signal()
        self.stb_stop = Signal()

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

        self.ref_ts = Signal(counter_width+n_fine)
        self.sig_ts = Signal(counter_width+n_fine)

        # In mu
        self.gate_start = Signal(14)
        self.gate_stop = Signal(14)

        # # #

        self.got_ref = Signal()

        # Absolute gate times, calculated when we get the reference event
        abs_gate_start = Signal(counter_width+n_fine)
        abs_gate_stop = Signal(counter_width+n_fine)

        t_ref = Signal(counter_width+n_fine)
        self.comb += t_ref.eq(Cat(phy_ref.fine_ts,m))

        self.sync += [
            If(phy_ref.stb_rising,
                self.got_ref.eq(1),
                self.ref_ts.eq(t_ref),
                abs_gate_start.eq(self.gate_start + t_ref),
                abs_gate_stop.eq(self.gate_stop + t_ref)
            ),
            If(self.clear,
                self.got_ref.eq(0),
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
            If(phy_sig.stb_rising & ~self.triggered & triggering,
                self.triggered.eq(triggering),
                self.sig_ts.eq(t_sig)
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
        self.m = Signal(counter_width) # Global cycle-relative time.
        self.time_remaining = Signal(32) # Clock cycles remaining before timeout
        self.time_remaining_buf = Signal(32)
        self.cycles_completed = Signal(14) # How many iterations of the loop have completed since last start

        self.run_stb = Signal() # Pulsed to start core running until timeout or success
        self.done_stb = Signal() # Pulsed when core has finished (on timeout or success)
        self.running = Signal() # Asserted on run_stb, cleared on done_stb

        self.timeout = Signal()
        self.success = Signal()

        self.ready = Signal()

        self.herald = Signal()

        self.is_master = Signal()
        self.standalone = Signal() # Asserted with is_master, ignore slave state for single-device testing

        self.trigger_out = Signal() # Trigger to slave

        # Unregistered inputs from master
        self.trigger_in_raw = Signal()
        self.success_in_raw = Signal()
        self.timeout_in_raw = Signal()

        # Unregistered input from slave
        self.slave_ready_raw = Signal()

        self.m_end = Signal(counter_width) # Number of clock cycles to run main loop for

        # Asserted while the entangler is idling, waiting for the entanglement cycle to
        # start.
        self.cycle_starting = Signal()

        self.cycle_ending = Signal()

        # # #

        self.comb += self.cycle_ending.eq(self.m == self.m_end)

        self.trigger_in = Signal()
        self.success_in = Signal()
        self.slave_ready = Signal()
        self.timeout_in = Signal()
        self.sync += [
            self.trigger_in.eq(self.trigger_in_raw),
            self.success_in.eq(self.success_in_raw),
            self.slave_ready.eq(self.slave_ready_raw),
            self.timeout_in.eq(self.timeout_in_raw)
        ]

        self.sync += [
            If(self.run_stb, self.running.eq(1)),
            If(self.done_stb, self.running.eq(0))
        ]


        # The core times out if time_remaining countdown reaches zero, or,
        # if we are a slave, if the master has timed out.
        # This is required to ensure the slave syncs with the master
        self.comb += self.timeout.eq( (self.time_remaining == 0)
                            | (~self.is_master & self.timeout_in))

        self.sync += [
            If(self.run_stb,
                self.time_remaining.eq(self.time_remaining_buf)
            ).Else(
                If(~self.timeout,
                    self.time_remaining.eq(self.time_remaining-1)))
        ]

        done = Signal()
        done_d = Signal()
        finishing = Signal()
        self.comb += finishing.eq( ~self.run_stb & self.running & (self.timeout | self.success))
        # Done asserted at the at the end of the successful / timedout cycle
        self.comb += done.eq(finishing & self.cycle_starting)
        self.comb += self.done_stb.eq(done & ~done_d)

        # Ready asserted when run_stb is pulsed, and cleared on success or timeout
        self.sync += [
            If(self.run_stb, self.ready.eq(1), self.cycles_completed.eq(0), self.success.eq(0)),
            done_d.eq(done),
            If(finishing, self.ready.eq(0))
        ]

        fsm = FSM()
        self.submodules += fsm

        fsm.act("IDLE",
            self.cycle_starting.eq(1),
            If(self.is_master,
                If(~finishing & self.ready & (self.slave_ready | self.standalone), NextState("TRIGGER_SLAVE"))
            ).Else(
                If(~finishing & self.ready & self.trigger_in, NextState("COUNTER"))
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
            If(self.cycle_ending,
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
    def __init__(self, core_link_pads, output_pads, output_sigs, input_phys, simulate=False):
        self.enable = Signal()
        # # #

        phy_apds = input_phys[0 : 4]
        phy_422pulse = input_phys[4]

        self.submodules.msm = MainStateMachine()

        self.submodules.sequencers = [ChannelSequencer(self.msm.m) for _ in range(4)]

        self.submodules.apd_gaters = [InputGater(self.msm.m, phy_422pulse, phy_apd)
                                      for phy_apd in phy_apds]

        self.submodules.heralder = Heralder(n_sig=4, n_patterns=4)

        if not simulate:
            # Connect output pads to sequencer output when enabled, otherwise use
            # the RTIO phy output
            for i in range(4):
                sequencer_sig = self.sequencers[i].output
                pad = output_pads[i]
                self.specials += Instance("OBUFDS",
                              i_I=Mux(self.enable, sequencer_sig, output_sigs[i]),
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

            # Interface between master and slave core.

            # Slave -> master:
            ts_buf(core_link_pads[0],
                self.msm.ready, self.msm.slave_ready_raw,
                ~self.msm.is_master & ~self.msm.standalone)

            # Master -> slave:
            ts_buf(core_link_pads[1],
                self.msm.trigger_out, self.msm.trigger_in_raw,
                self.msm.is_master & ~self.msm.standalone)
            ts_buf(core_link_pads[2],
                self.msm.success, self.msm.success_in_raw,
                self.msm.is_master & ~self.msm.standalone)
            ts_buf(core_link_pads[3],
                self.msm.timeout, self.msm.timeout_in_raw,
                self.msm.is_master & ~self.msm.standalone)

        # Connect heralder inputs.
        self.comb += self.heralder.sig.eq(Cat(*(g.triggered for g in self.apd_gaters)))

        # Clear gater and sequencer state at start of each cycle
        self.comb += [gater.clear.eq(self.msm.cycle_starting)
                            for gater in self.apd_gaters]
        self.comb += [sequencer.clear.eq(self.msm.cycle_starting)
                            for sequencer in self.sequencers]

        self.comb += self.msm.herald.eq(self.heralder.herald)

        # 422ps trigger event counter. We use got_ref from the first gater for
        # convenience (any other channel would work just as well).
        self.triggers_received = Signal(14)
        self.sync += [
            If(self.msm.run_stb,
                self.triggers_received.eq(0)
            ).Else(
                If(self.msm.cycle_ending & self.apd_gaters[0].got_ref,
                    self.triggers_received.eq(self.triggers_received+1)
                )
            )
        ]
