from uldaq import get_daq_device_inventory, DaqDevice, InterfaceType, AiInputMode, Range, AOutFlag, AInFlag, ULException

import time
import logging

from PyQt5 import QtTest


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

        except ULException as e:
            logging.error(f"\n{e}")

    def set_starting_temp(self, t):
        self.ao.a_out(channel=0, analog_range=Range.BIP10VOLTS, flags=AOutFlag.DEFAULT, data=t*10e-3)

    def set_temperature(self, t_target):
        v_aout = t_target * 10.0e-3

        logging.debug(f"Value to be set in AOUT0: {v_aout}")
        self.ao.a_out(channel=0, analog_range=Range.BIP10VOLTS, flags=AOutFlag.DEFAULT, data=v_aout)

        # Check if setpoint is correct
        t_setpoint = self.get_setpoint_temp()
        t_diff = t_target - t_setpoint

        while t_diff > 0.01:
            v_aout = (t_target + t_diff) * 10.0e-3

            logging.debug(f'Value to be set in AOUT0: {v_aout}')
            self.ao.a_out(channel=0, analog_range=Range.BIP10VOLTS, flags=AOutFlag.DEFAULT, data=v_aout)

            # Check if setpoint is correct
            t_setpoint = self.get_setpoint_temp()
            t_diff = t_target - t_setpoint

    def get_bath_temp(self, samples=100, interval=1e-3):
        tmp = []

        for i in range(samples):
            QtTest.QTest.qWait(interval)
            # time.sleep(interval)

            a_in = self.ai.a_in(channel=5, input_mode=AiInputMode.DIFFERENTIAL, analog_range=Range.BIP10VOLTS,
                                flags=AInFlag.DEFAULT)
            tmp.append(a_in)

        return (sum(tmp) / len(tmp)) * 100

    def get_setpoint_temp(self, samples=100, interval=1e-3):
        tmp = []
    
        for i in range(samples):
            QtTest.QTest.qWait(interval)
            # time.sleep(interval)

            a_in = self.ai.a_in(channel=4, input_mode=AiInputMode.DIFFERENTIAL, analog_range=Range.BIP10VOLTS,
                                flags=AInFlag.DEFAULT)
            tmp.append(a_in)

        return (sum(tmp) / len(tmp)) * 100
