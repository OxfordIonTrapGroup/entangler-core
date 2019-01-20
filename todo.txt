- Test:
    - Does the core time-out correctly if only master or slave running
    - Do the master and slave cores agree on the number of cycles
    - Do the master and slave cores synchronize


---

Input timestamp resolution is 1ns
Max cycle length is ~10us
So lets use 14 bits per timestamp (16.38us max)

Core should only be enabled after sensible values are loaded into the registers.
E.g. if n_cycles=0 when the core is enabled it will saturate the ififo with timeout events...


Registers:
0b0000 : Config : w:
    from low to high bits [enable, is_master, standalone]
    set if master or slave, set if core enabled (i.e. un-tris master / slave outputs, override output phys)
0b0001 : Run : w: trigger sequence on write, set max time to run for
0b0010 : Cycle length: w:
0b0011 : Heralds: w: 4x 4 bit heralds, then 4 bits of herald enable flags (to allow working with fewer heralds) -> 20 bits

Timing registers: 4x outputs, 4x gating inputs
Each has 14 bits t_start, 14 bits t_end -> 32 bits (to align top to dword)
0b1_000 ... 0b1_110


0b10_000 : Status: r: core running?
0b10_001 : NCycles: r: How many cycles have been completed (reset every write to 'run') (14 bits, will roll over!)
5x timestamps: r: 14 bits each
0b11_000 ... 0b11_100

So bits[4:3] = 0 for low reg writes, 1 for timing reg writes, 2 for status reads, 3 for timestamp reads


The smallest time stamp that is valid for output events is 1 (0 makes the output stay off permantly)
