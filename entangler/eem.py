

class Entangler(_EEM):
    @staticmethod
    def io(eem_interface, eem_dio):
        ios = [("dio{}".format(eem_dio), i,
            Subsignal("p", Pins(_eem_pin(eem_dio, i, "p"))),
            Subsignal("n", Pins(_eem_pin(eem_dio, i, "n"))),
            IOStandard("LVDS_25"))
            for i in range(8)]
        ios += [("if{}".format(eem_interface), i,
            Subsignal("p", Pins(_eem_pin(eem_interface, i, "p"))),
            Subsignal("n", Pins(_eem_pin(eem_interface, i, "n"))),
            IOStandard("LVDS_25"))
            for i in range(8)]
        return ios

    @classmethod
    def add_std(cls, target, eem_interface, eem_dio):
        cls.add_extension(target, eem_interface, eem_dio)

        output_pads = []
        output_sigs = [Signal() for _ in range(4)]
        for i in range(4):
            pads = target.platform.request("dio{}".format(eem_dio), i)
            output_pads += pads
            phy = ttl_simple.Output(output_sigs[i])
            target.submodules += phy
            target.rtio_channels.append(rtio.Channel.from_phy(phy))

        input_phys = []
        for i in range(4):
            pads = target.platform.request("dio{}".format(eem_dio), 4+i)
            phy = ttl_serdes_7series.Input_8x(pads.p, pads.n)
            target.submodules += phy
            input_phys += phy
            target.rtio_channels.append(rtio.Channel.from_phy(phy))

        if_pads = [target.platform.request("if{}".format(eem_interface), i)
                    for i in range(8)]
        phy = EntanglerCore(if_pads, output_pads, output_sigs, input_phys)
        target.rtio_channels.append(rtio.Channel.from_phy(phy))