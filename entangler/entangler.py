from artiq.language.core import kernel, delay, now_mu, delay_mu, portable
from artiq.language.units import us, ns
from artiq.coredevice.rtio import rtio_output, rtio_input_data

# Write only
ADDR_W_CONFIG = 0
ADDR_W_ENABLE = 1
ADDR_W_DURATION = 2
ADDR_W_T_CYCLE = 3
ADDR_W_HERALD = 4

# Read only
ADDR_R_STATUS = 5
ADDR_R_NCYCLES = 6
TS_422PULSE = 7
TS_APD1E = 8
TS_APD1L = 9
TS_APD2E = 10
TS_APD2L = 11


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

    def _seconds_to_coarse_mu(self, t):
        t_mu = self.core.seconds_to_mu(t)
        return t_mu >> 3

    @kernel
    def init(self):
        self.write(ADDR_ISMASTER, self.is_master)

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
    def set_config(self, enable):
        """
        """
        self.write(CONFIG_ADDR, enable)

    @kernel
    def set_timing(self, channel, t_start, t_stop=0):
        # Round start and stop to the coarse clock
        n_start = self._seconds_to_coarse_mu(t_start) & 0x3fff
        n_stop = self._seconds_to_coarse_mu(t_stop) & 0x3fff
        self.write(channel, n_start | (n_stop>>16))

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
