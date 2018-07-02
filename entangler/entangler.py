from artiq.language.core import kernel, delay, now_mu, delay_mu, portable
from artiq.language.units import us, ns
from artiq.coredevice.rtio import rtio_output, rtio_input_data

# Write only
ADDR_W_CONFIG = 0
ADDR_W_RUN = 1
ADDR_W_T_CYCLE = 2
ADDR_W_HERALD = 3

# Output channel addresses
out_1092 = 0b1000+0
out_422sigma = 0b1000+1
out_422pulsed_trigger = 0b1000+2
out_misc = 0b1000+3
gate_apd1_a = 0b1000+4
gate_apd1_b = 0b1000+5
gate_apd2_a = 0b1000+6
gate_apd2_b = 0b1000+7

# Read only
ADDR_R_STATUS = 0b10000
ADDR_R_NCYCLES = 0b10000+1
ts_422PULSE = 0b11000+0
ts_APD1A = 0b11000+1
ts_APD1B = 0b11000+2
ts_APD2A = 0b11000+3
ts_APD2B = 0b11000+4


class Entangler:
    """
    Sequences remote entanglement experiments between a master and a slave

    :param channel: RTIO channel number
    :param is_master: Is this Kasli the sequencer master or the slave
    :param core_device: Core device name
    """
    def __init__(self, dmgr, channel, is_master=True, core_device="core"):
        self.core = dmgr.get(core_device)
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
        """
        Configure the core:
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
    def set_timing(self, channel, t_start, t_stop):
        """Set the output channel timing and relative gate times.
        
        Times are in seconds.
        For output channels the timing resolution is the coarse clock (8ns), and
        the times are relative to the start of the entanglement cycle.
        For gate channels the time is relative to the reference pulse (422
        pulse input) and has fine timing resolultion (1ns)
        """
        mu_start = self.core.seconds_to_mu(t_start)
        mu_stop = self.core.seconds_to_mu(t_stop)

        if channel < gate_apd1_a:
            mu_start = mu_start >> 3
            mu_stop = mu_stop >> 3

        # Truncate to 14 bits
        mu_start &= 0x3fff
        mu_stop &= 0x3fff
        self.write(channel, (mu_stop<<16) | mu_start)

    @kernel
    def set_cycle_length(self, t_cycle):
        """Set the entanglement cycle length.

        If the herald module does not signal success by this time the loop
        repeats. Resolution is coarse_ref_period."""
        self.write(self.ADDR_T_CYCLE, self._seconds_to_coarse_mu(t_cycle))

    @kernel
    def set_heralds(self, *heralds):
        """Set the count patterns that cause the entangler loop to exit
        Up to 4 patterns can be set."""
        data = 0
        for i in range(min(4,len(heralds))):
            data |= ((1<<5) | (heralds[i] & 0xf)) << (5*i)
        self.write(self.ADDR_W_HERALD, data)

    @kernel
    def run(self, duration):
        """Run the entanglement sequence until success, or duration has elapsed.

        Returns -1 if there was a timeout, or the herald pattern if there was
        a success (herald pattern match).
        """

        rtio_output(now_mu(), self.channel, ADDR_DURATION, self.core.seconds_to_mu(duration))
        return rtio_input_data(self.channel)

    @kernel
    def get_status(self):
        return self.read(ADDR_R_STATUS)

    @kernel
    def get_ncycles(self):
        """Get the number of cycles the core has currently run for.
        Reset when ???
        """
        return self.read(ADDR_R_NCYCLES)

    @kernel
    def get_timestamp(self, index):
        """Get the timestamp given by index"""
        return self.read(index)
