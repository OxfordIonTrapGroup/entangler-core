from artiq.language.core import kernel, delay, now_mu, delay_mu, portable
from artiq.language.units import us, ns
from artiq.coredevice.rtio import rtio_output, rtio_input_data, rtio_input_timestamp_data
import numpy as np

# Write only
ADDR_W_CONFIG = 0
ADDR_W_RUN = 1
ADDR_W_TCYCLE = 2
ADDR_W_HERALD = 3

# Output channel addresses
sequencer_422sigma = 0b1000+0
sequencer_1092 = 0b1000+1
sequencer_422ps_trigger = 0b1000+2
sequencer_aux = 0b1000+3
gate_apd0 = 0b1000+4
gate_apd1 = 0b1000+5
gate_apd2 = 0b1000+6
gate_apd3 = 0b1000+7

# Read only
ADDR_R_STATUS = 0b10000
ADDR_R_NCYCLES = 0b10000+1
ADDR_R_TIMEREMAINING = 0b10000+2
ADDR_R_NTRIGGERS = 0b10000+3
timestamp_apd0 = 0b11000+0
timestamp_apd1 = 0b11000+1
timestamp_apd2 = 0b11000+2
timestamp_apd3 = 0b11000+3
timestamp_422ps = 0b11000+4


class Entangler:
    """Sequences remote entanglement experiments between a master and a slave

    :param channel: RTIO channel number
    :param is_master: Is this Kasli the sequencer master or the slave
    :param core_device: Core device name
    """
    def __init__(self, dmgr, channel, is_master=True, core_device="core"):
        self.core = dmgr.get(core_device)
        self.channel = channel
        self.is_master = is_master
        self.ref_period_mu = self.core.seconds_to_mu(
            self.core.coarse_ref_period)

    @kernel
    def init(self):
        self.set_config() # Write is_master

    @kernel
    def write(self, addr, value):
        """Write parameter.

        This method advances the timeline by one coarse RTIO cycle.

        :param addr: parameter address.
        :param value: Data to be written.
        """
        rtio_output(now_mu(), self.channel, addr, value)
        delay_mu(self.ref_period_mu)

    @kernel
    def read(self, addr):
        """Read parameter

        This method does not advance the timeline but consumes all slack.

        :param addr: Memory location address.
        """
        rtio_output(now_mu(), self.channel, addr, 0)
        return rtio_input_data(self.channel)

    @kernel
    def set_config(self, enable=False, standalone=False):
        """Configure the core

        enable: allow core to drive outputs (otherwise they are connected to
            normal TTLOut phys). Do not enable if the cycle length and timing
            parameters are not set.
        standalone: don't attempt syncronisation with partner, just run when
            ready. Used for testing and single-trap mode
        """
        data = 0
        if enable:
            data |= 1
        if self.is_master or standalone:
            data |= 1<<1
        if standalone:
            data |= 1<<2
        self.write(ADDR_W_CONFIG, data)

    @kernel
    def set_timing_mu(self, channel, t_start_mu, t_stop_mu):
        """Set the output channel timing and relative gate times.

        Times are in machine units.
        For output channels the timing resolution is the coarse clock (8ns), and
        the times are relative to the start of the entanglement cycle.
        For gate channels the time is relative to the reference pulse (422
        pulse input) and has fine timing resolultion (1ns).

        The start / stop times can be between 0 and the cycle length.
        (i.e for a cycle length of 100*8ns, stop can be at most 100*8ns)
        If the stop time is after the cycle length, the pulse stops at the cycle
        length. If the stop is before the start, the pulse stops at the cycle
        length. If the start is after the cycle length there is no pulse.
        """
        if channel < gate_apd1_a:
            t_start_mu = t_start_mu >> 3
            t_stop_mu = t_stop_mu >> 3

        t_start_mu += 1
        t_stop_mu += 1

        # Truncate to 14 bits
        t_start_mu &= 0x3fff
        t_stop_mu &= 0x3fff
        self.write(channel, (t_stop_mu<<16) | t_start_mu)

    @kernel
    def set_timing(self, channel, t_start, t_stop):
        """Set the output channel timing and relative gate times.

        Times are in seconds. See set_timing_mu() for details"""
        t_start_mu = np.int32(self.core.seconds_to_mu(t_start))
        t_stop_mu = np.int32(self.core.seconds_to_mu(t_stop))
        self.set_timing_mu(channel, t_start_mu, t_stop_mu)

    @kernel
    def set_cycle_length_mu(self, t_cycle_mu):
        """Set the entanglement cycle length.

        If the herald module does not signal success by this time the loop
        repeats. Resolution is coarse_ref_period."""
        t_cycle_mu = t_cycle_mu >> 3
        self.write(ADDR_W_TCYCLE, t_cycle_mu)

    @kernel
    def set_cycle_length(self, t_cycle):
        """Set the entanglement cycle length.

        Times are in seconds."""
        t_cycle_mu = np.int32(self.core.seconds_to_mu(t_cycle))
        self.set_cycle_length_mu(t_cycle_mu)

    @kernel
    def set_heralds(self, heralds):
        """Set the count patterns that cause the entangler loop to exit

        Up to 4 patterns can be set.
        Each pattern is a 4 bit number, with the order (LSB first)
        apd1_a, apd1_b, apd2_a, apd2_b.
        E.g. to set a herald on apd1_a only: set_heralds(0b0001)
        to herald on apd1_b, apd2_b: set_heralds(0b1010)
        To herald on both: set_heralds(0b0001, 0b1010)
        """
        data = 0
        assert len(heralds) <= 4
        for i in range(len(heralds)):
            data |= (heralds[i] & 0xf) << (4*i)
            data |= 1<<(16+i)
        self.write(ADDR_W_HERALD, data)

    @kernel
    def run_mu(self, duration_mu):
        """Run the entanglement sequence until success, or duration (in seconds)
        has elapsed. Blocking.

        Returns a tuple of [timestamp, reason]
        timestamp is the RTIO time at the end of the final cycle.
        reason is 0x3fff if there was a timeout, or a bitfield giving the
        herald matches if there was a success.
        """
        duration_mu = duration_mu >> 3
        rtio_output(now_mu(), self.channel, ADDR_W_RUN, duration_mu)
        return rtio_input_timestamp_data(self.channel)

    @kernel
    def run(self, duration):
        """Run the entanglement sequence. See run_mu() for details.

        Duration is in seconds"""
        duration_mu = np.int32(self.core.seconds_to_mu(duration))
        return self.run_mu(duration_mu)

    @kernel
    def get_status(self):
        return self.read(ADDR_R_STATUS)

    @kernel
    def get_ncycles(self):
        """Get the number of cycles the core has completed since the last call to run()
        """
        return self.read(ADDR_R_NCYCLES)

    @kernel
    def get_ntriggers(self):
        """Get the number of 422pulsed triggers the core has received since the
        last call to run()
        """
        return self.read(ADDR_R_NTRIGGERS)

    @kernel
    def get_time_remaining(self):
        """Get the number of remaining number of clock cycles the core will
        run for before timing out
        """
        return self.read(ADDR_R_TIMEREMAINING)

    @kernel
    def get_timestamp_mu(self, channel):
        """Get the input timestamp for a channel

        The timestamp is the time offset, in mu, from the start of the cycle to
        the detected rising edge.
        """
        return self.read(channel)
