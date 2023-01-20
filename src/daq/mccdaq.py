from uldaq import get_daq_device_inventory, DaqDevice, InterfaceType, AiInputMode, Range, AOutFlag, AInFlag, ULException

import time
import logging


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

        self.ao.a_out(channel=0, analog_range=Range.BIP10VOLTS, flags=AOutFlag.DEFAULT, data=t*10e-3)

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
        t_setpoint = self.read_setpoint_temp()
        t_diff = t_target - t_setpoint

        while abs(t_diff) > 0.01:
            v_aout = (t_target + t_diff) * 10.0e-3

            logging.debug(f'Value to be set in AOUT0: {v_aout}')
            self.ao.a_out(channel=0, analog_range=Range.BIP10VOLTS, flags=AOutFlag.DEFAULT, data=v_aout)

            # Check the new setpoint
            t_setpoint = self.read_setpoint_temp()
            t_diff = t_target - t_setpoint

    def read_bath_temp(self):
        """
        Reads the bath temperature from channel 5 of the USB-1808 device.

        Returns
        -------
        float
            float value representing the temperature in degree Celsius.

        Example
        -------
        read_bath_temp() -> 20.5
        """

        a_in = self.ai.a_in(channel=5,
                            input_mode=AiInputMode.DIFFERENTIAL,
                            analog_range=Range.BIP10VOLTS,
                            flags=AInFlag.DEFAULT)

        return a_in / 10e-3

    def read_setpoint_temp(self):
        """
        Reads the setpoint temperature from channel 4 of the USB-1808 device.

        Returns
        -------
        float
            float value representing the temperature in degree Celsius.

        Example
        -------
        read_setpoint_temp() -> 22.3
        """

        a_in = self.ai.a_in(channel=4,
                            input_mode=AiInputMode.DIFFERENTIAL,
                            analog_range=Range.BIP10VOLTS,
                            flags=AInFlag.DEFAULT)

        return a_in / 10e-3
