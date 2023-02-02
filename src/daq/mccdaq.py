from uldaq import get_daq_device_inventory, DaqDevice, InterfaceType, AiInputMode, Range, AOutFlag, AInFlag, ULException
from uldaq import create_float_buffer, ScanStatus

import time
import logging
import numpy as np

NUMBER_OF_CHANNELS = 2
SAMPLES_PER_CHANNEL = 500
SAMPLING_RATE = 1000  # In samples per channel per second


class Daq:
    """
    Daq class is used to interact with a USB-1808 DAQ device from MCCDAQ to perform functions such as setting the
    temperature and reading the bath temperature and setpoint temperature.
    """
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

            self.data_buffer = create_float_buffer(NUMBER_OF_CHANNELS, SAMPLES_PER_CHANNEL)

            logging.info(f'MCCDAQ Connected!')

        except ULException as e:
            logging.error(f"\n{e}")

    def set_starting_temp(self, t):
        """
        Sets the starting temperature on channel 0 of the USB-1808 device.

        Parameters
        ----------
        t : float
            float value representing the temperature in degree Celsius.

        Example
        -------
        set_starting_temp(20)
        """

        self.ao.a_out(channel=0, analog_range=Range.BIP10VOLTS, flags=AOutFlag.DEFAULT, data=t * 10e-3)

    def set_temperature(self, t_target):
        """
        Sets the temperature on channel 0 of the USB-1808 device.

        The method will iterate reading the setpoint and adjusting the output voltage until setpoint reaches the correct
        value.

        Parameters
        ----------
        t_target : float
            float value representing the target temperature in degree Celsius.

        Example
        -------
        set_temperature(25)
        """

        v_aout = t_target * 10.0e-3

        logging.debug(f"Value to be set in AOUT0: {v_aout}")
        self.ao.a_out(channel=0, analog_range=Range.BIP10VOLTS, flags=AOutFlag.DEFAULT, data=v_aout)

        # Check if setpoint is correct
        t_setpoint = self.read_all_temp()[1]
        t_diff = t_setpoint - t_target

        while abs(t_diff) > 0.05:
            print(abs(t_diff))
            v_aout = v_aout - (t_diff * 10.0e-3)

            logging.debug(f'Value to be set in AOUT0: {v_aout}')
            self.ao.a_out(channel=0, analog_range=Range.BIP10VOLTS, flags=AOutFlag.DEFAULT, data=v_aout)

            # Check the new setpoint
            t_setpoint = self.read_all_temp()[1]
            t_diff = t_setpoint - t_target

    def read_all_temp(self):
        """
        Reads the setpoint temperature from channel 4 of the USB-1808 device.

        Returns
        -------
        tuple[float,float,float,float,float]
            float value representing the temperature in degree Celsius.

        Example
        -------
        read_setpoint_temp() -> 22.3
        """
        while self.ai.get_scan_status()[0] != ScanStatus.IDLE:
            time.sleep(0.01)

        self.ai.a_in_scan(4, 5, input_mode=AiInputMode.DIFFERENTIAL, analog_range=Range.BIP10VOLTS,
                          flags=AInFlag.DEFAULT, samples_per_channel=SAMPLES_PER_CHANNEL, rate=SAMPLING_RATE, options=0, data=self.data_buffer)

        data = np.array(self.data_buffer[:]).reshape((SAMPLES_PER_CHANNEL, NUMBER_OF_CHANNELS)).transpose().mean(axis=1)

        bt = data[1] / 10e-3
        sp = data[0] / 10e-3

        self.ai.scan_wait(0, -1)

        return bt, sp






