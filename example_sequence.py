# Device db sets is_master flag

entangler.init() # writes is_master

# Pulse on and off times, granularity 8*ns
entangler.set_timing(entangler._422sigma, 30*ns, 500*ns)
entangler.set_timing(entangler._1092, 0*ns, 450*ns)

# 422pulse trigger output, granularity 8*ns
entangler.set_timing(entangler._422pulse, 580*ns)

# Offsets between 422pulse trigger input and apd gate, granularity 1*ns
entangler.set_gate_offset(entangler.apd_1_early, 39*ns, 50*ns)
entangler.set_gate_offset(entangler.apd_1_late, 70*ns, 85*ns)
entangler.set_gate_offset(entangler.apd_2_early, 35*ns, 48*ns)
entangler.set_gate_offset(entangler.apd_2_late, 68*ns, 83*ns)

# The entanglement cycle length. If the herald module does not signal success
# by this time the loop repeats
entangler.set_cycle_length(1.05*us)

# Set the count patterns that cause the entangler loop to exit
# Up to 4 patterns can be set.
entangler.set_heralds([0,1,0,1], [1,0,0,1], [0,1,1,0], [1,0,1,0])


while True:
    doppler_cool(20*us)

    # Enable the override switches
    entangler.set_config(enable=True)
    delay(10*ns)
    _422sigma.sw.on()
    _1092.sw.on()
    _422pulsed.sw.on()
    # DMA from stops here

    # Run entangler core until sucess, or 200*us has elapsed
    # (finishes at the end of the current cycles)
    r = entangler.run(200*us)

    _422pulsed.sw.off()
    _1092.sw.off()
    _422sigma.sw.off()
    entangler.set_config(enable=False)

    if r:
        break


# Get herald
entangler.get_herald_pattern()


# Number of entanglement cycles run since last enable
n = entangler.get_n_cycles()