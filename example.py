

e = Entangler(pads, [phy_apd_1, phy_apd_2])

mem = rtservo.RTServoMem(iir_p, su)
target.submodules += mem
target.rtio_channels.append(rtio.Channel.from_phy(mem, ififo_depth=4))