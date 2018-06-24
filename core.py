from migen import *

counter_width = 10


class ChannelSequencer(Module):
    def __init__(self):
        self.m = Signal(counter_width) # Counter
        self.m_start = Signal(counter_width)
        self.m_stop = Signal(counter_width)
        self.clear = Signal()

        self.stb_start = Signal()
        self.stb_stop = Signal()

        self.output = Signal()

        ###

        self.comb += [
            self.stb_start.eq(self.m == self.m_start),
            self.stb_stop.eq(self.m == self.m_stop)
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
    """Simple event gater that connects to the ISERDES of a ttl_serdes_generic
    phy.

    Latches rising edge events when the gate is open, and asserts the triggered
    flag. The module is reset (triggered flag cleared) by asserting clear.
    """
    def __init__(self, phy=None):
        self.m = Signal() # Counter
        self.gate = Signal() # Asserted when we should register events
        self.clear = Signal()

        self.triggered = Signal()
        self.coarse_ts = Signal(counter_width)
        self.fine_ts = Signal(len(phy.fine_ts))
        ###

        self.sync += [
            If(self.gate & phy.stb_rising,
                self.triggered.eq(1),
                self.fine_ts.eq(phy.fine_ts),
                self.coarse_ts.eq(m)
            ),
            If(self.clear, self.triggered.eq(0))
        ]


class Heralder(Module):
    """Asserts 'herald' if input vector matches any pattern in patterns"""
    def __init__(self, n_sig = 4, n_patterns=1):
        self.sig = Signal(n_sig)
        self.patterns = [Signal(n_sig) for _ in range(n_patterns)]

        self.herald = Signal()

        ###

        self.comb += self.herald.eq( 0 != Cat(*[p == self.sig for p in self.patterns]))


class MainStateMachine(Module):
    def __init__(self):
        self.m = Signal(counter_width)
        self.cycles_remaining = Signal(16)
        self.run = Signal()
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

        self.comb += self.ready.eq( (self.cycles_remaining != 0) & self.run & ~self.success)

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
                NextValue(self.cycles_remaining, self.cycles_remaining-1),
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





class Entangler(Module):
    def __init__(self, pads, phy_apds):
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
            self.msm.
        ]




