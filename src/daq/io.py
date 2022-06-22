from uldaq import get_daq_device_inventory, DaqDevice, InterfaceType, AiInputMode, Range, AOutFlag, AInFlag, ULException

import time


class Daq:
    def __init__(self):
        try:
            devices = get_daq_device_inventory(InterfaceType.USB)

            # Create a DaqDevice Object and connect to the device
            self.daq_device = DaqDevice(devices[0])
            self.daq_device.connect()

            # Get AoDevice and AoInfo objects for the analog input subsystem
            self.ao = self.daq_device.get_ao_device()
            self.ao.info = self.ao.get_info()

            # Get AiDevice and AiInfo objects for the analog input subsystem
            self.ai = self.daq_device.get_ai_device()
            self.ai.info = self.ai.get_info()

            self.temp_setpoint = 16

        except ULException as e:
            print('\n', e)

    def set_reference_voltage(self):

        self.ao.a_out(channel=1,
                      analog_range=Range.BIP10VOLTS,
                      flags=AOutFlag.DEFAULT,
                      data=9)

    def set_temperature(self, temp):

        self.ao.a_out(channel=0,
                      analog_range=Range.BIP10VOLTS,
                      flags=AOutFlag.DEFAULT,
                      data=(temp - self.temp_setpoint) / 100)

    def get_bath_temp(self, samples=100, interval=1e-3):
        tmp = []
        for i in range(samples):
            time.sleep(interval)
            a_in = self.ai.a_in(channel=5, input_mode=AiInputMode.DIFFERENTIAL, analog_range=Range.BIP10VOLTS,
                                flags=AInFlag.DEFAULT)
            tmp.append(a_in)

        return sum(tmp) / len(tmp)

    def get_setpoint_temp(self, samples=100, interval=1e-3):
        tmp = []
        for i in range(samples):
            time.sleep(interval)
            a_in = self.ai.a_in(channel=4, input_mode=AiInputMode.DIFFERENTIAL, analog_range=Range.BIP10VOLTS,
                                flags=AInFlag.DEFAULT)
            tmp.append(a_in)

        return sum(tmp) / len(tmp)
