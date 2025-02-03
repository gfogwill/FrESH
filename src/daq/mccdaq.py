import uldaq
from uldaq import get_daq_device_inventory, DaqDevice, InterfaceType, AiInputMode, Range, AOutFlag, AInFlag, ULException
from uldaq import create_float_buffer, ScanOption, ScanStatus

import time
import logging
import numpy as np


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
            # add comment

            # Get AoDevice and AoInfo objects for the analog input subsystem
            self.ao = self.daq_device.get_ao_device()
            self.ao.info = self.ao.get_info()

            # Get AiDevice and AiInfo objects for the analog input subsystem
            self.ai = self.daq_device.get_ai_device()
            self.ai.info = self.ai.get_info()

            self.ao.a_out(channel=1, analog_range=Range.BIP10VOLTS, flags=AOutFlag.DEFAULT, data=5)

            self.data_buffer = create_float_buffer(7, 500)
            self.ts = 0
            # self.ai.a_in_scan(0, 6, input_mode=AiInputMode.DIFFERENTIAL, analog_range=Range.BIP10VOLTS,
            #                   flags=AInFlag.DEFAULT, samples_per_channel=1, rate=1, options=ScanOption.SINGLEIO,
            #                   data=self.data_buffer)

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

        self.ao.a_out(channel=1, analog_range=Range.BIP10VOLTS, flags=AOutFlag.DEFAULT, data=t * 10e-3)

    def set_temperature(self, t_target, max_iterations=50, tolerance=0.08, Kp=0.9):
        """
        Sets the temperature on channel 0 of the USB-1808 device using a proportional control method.

        Parameters
        ----------
        t_target : float
            Target temperature in degree Celsius.
        max_iterations : int, optional
            Maximum number of iterations to attempt reaching the target temperature (default is 50).
        tolerance : float, optional
            Acceptable difference between setpoint and target temperature (default is 0.08).
        Kp : float, optional
            Proportional gain for scaling the voltage adjustments (default is 0.9).
        """
        v_aout = t_target * 10.0e-3
        logging.info(f"Setting temperature to: {t_target}")
        logging.debug(f"Initial AOUT0 value: {v_aout}")

        # Set the initial voltage output
        self.ao.a_out(channel=1, analog_range=Range.BIP10VOLTS, flags=AOutFlag.DEFAULT, data=v_aout)

        for i in range(max_iterations):
            # Read current setpoint temperature
            t_setpoint = self.read_all_temp()[1]
            t_diff = t_setpoint - t_target

            logging.debug(f"Iteration {i + 1}: t_setpoint: {t_setpoint}, t_diff: {t_diff}")

            if abs(t_diff) <= tolerance:
                logging.info(f"Temperature set successfully: {t_setpoint}")
                break

            # Calculate the adjustment based on the proportional control
            adjustment = Kp * t_diff * 10.0e-3

            # Adjust output voltage
            v_aout -= adjustment

            logging.debug(f"Iteration {i + 1}: Adjusting AOUT0 to {v_aout} (adjustment: {adjustment})")
            self.ao.a_out(channel=1, analog_range=Range.BIP10VOLTS, flags=AOutFlag.DEFAULT, data=v_aout)

            # Add a small delay between adjustments to allow the system to stabilize
            time.sleep(0.1)

        else:
            logging.warning("Max iterations reached without hitting the target temperature.")

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

        self.ai.a_in_scan(0, 6, input_mode=AiInputMode.DIFFERENTIAL, analog_range=Range.BIP10VOLTS,
                          flags=AInFlag.DEFAULT, samples_per_channel=500, rate=1000, options=0, data=self.data_buffer)

        data = np.array(self.data_buffer[:]).reshape((500, 7)).transpose().mean(axis=1)

        ch0 = data[0]
        ch1 = data[1]
        temp = (data[2] * 100) - 40  # (data[2] - 1.25) / 5e-3
        rh = data[3] * 100  # (data[3] - 1.25) / 5e-3
        ch6 = data[6]

        sp = data[4] / 10e-3
        bt = data[5] / 10e-3

        self.ai.scan_wait(0, -1)

        # print(f"Temp:{tc3:.3f}\tRH:{tc4:.2f}")
        return bt, sp, ch0, ch1, temp, rh, ch6
