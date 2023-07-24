
import serial
import serial.tools.list_ports

import time
import logging

from src.daq.ADAMlib import ADAMConnection, ADAM4015
from src.daq import mccdaq

def read_command(connection, command: str):

    connection.write(command.encode('ASCII'))
    result = connection.readline()
    try:
        result = float(result.decode('ASCII'))
        return result
    except (ValueError, TypeError):
        return None


class LAUDARK20:
    def __init__(self, ini):
        self.ini = ini
        self.init_temp = 0

    def connect(self):
        logging.info("Connecting ADAM")

        conn = ADAMConnection(self.ini['SERIAL'])
        self.adam = ADAM4015(conn, 0x24, chs_to_enable=[0, 1])

        logging.info("ADAM Connected")
        logging.info("Connecting MC-DAQ")

        # Connect MC-DAQ (USB-1808) and set the initial temperature
        self.daq = mccdaq.Daq()
        self.daq.set_starting_temp(self.init_temp)

        logging.info("MC-DAQ Connected")

    def get_data(self):
        s0, s1 = self.adam.GetAllTemps()
        bt, sp, t1, t2, temp, rh, t5 = self.daq.read_all_temp()

        data = {'BT': bt, 'SP': sp, 'RTD0': s0, 'RTD1': s1, 't1': t1, 't2': t2, 'TEMP': temp, 'RH': rh, 't5': t5}

        return data


class LAUDARP1845:
    """
    LAUDA class is used to interact with a USB connected LAUDA PROline RP 1845 chiller to perform functions such
    as setting the temperature and reading the path temperature and set point temperature
    """

    def __init__(self):
        pass

    def connect(self):
        try:
            self.ports = serial.tools.list_ports.comports()
            for port_no, description, address in self.ports:
                if 'USB' in description:
                    self.port = str(port_no.format('ASCII'))
                    break
            self.ser = serial.Serial(self.port, timeout=0.5)
            time.sleep(1)

        except serial.SerialException:
            logging.error(f"Connection failed")

    def get_data(self):
        data = None

        try:
            s0, s1 = self.GetAllTemps()
            bt, sp, t1, t2, temp, rh, t5 = self.read_all_temp()

            data = {'BT': bt,
                    'SP': sp,
                    'RTD0': s0,
                    'RTD1': s1,
                    't1': t1,
                    't2': t2,
                    'TEMP': temp,
                    'RH': rh,
                    't5': t5}

            self.read_data_signal.emit(data)
        except (ValueError, TypeError):
            logging.info('No values!')

        return data

    def set_starting_temp(self, t):
        """
        Sets the starting temperature on the USB device
        :param t: float value representing the temperature in °C
        :return: None
        :example: set_starting_temp(20)
        """
        self.ser.write(f"OUT_SP_00_{t}\r".encode('ASCII'))
        time.sleep(1)

    def set_temperature(self, t_target):

        self.ser.write(f"OUT_SP_00_{t_target}\r".encode('ASCII'))
        time.sleep(1)

    def read_all_temp(self):

        # Read bath temperature (outflow temperature).
        bt = read_command(self.ser, "IN_PV_00\r")
        # Read temperature setpoint.
        sp = read_command(self.ser, "IN_SP_00\r")
        # Indication of the controlled temperature (int./ ext. Pt/ ext. Analogue/ ext. Serial).
        t1 = read_command(self.ser, "IN_PV_01\r")
        # Read current overtemperature switch-off point.
        t2 = read_command(self.ser, "IN_SP_03\r")
        # Read bath temperature (outflow temperature) in 0.001°C.
        temp = read_command(self.ser, "IN_PV_10\r")
        # Interrogation of the setpoint offset
        rh = read_command(self.ser, "IN_PAR_14\r")
        # Interrogation of the maximum outflow temperature limit
        t5 = read_command(self.ser, "IN_PAR_09\r")

        if None in [bt, sp, t1, t2, temp, rh, t5]:
            logging.info('No values!')
        else:
            return bt, sp, t1, t2, temp, rh, t5

    def GetTemp(self):
        """
        :return: External temperature TE (Pt100) in 0.001°C reading
        """
        self.ser.write(b"IN_PV_13\r")
        t = self.ser.readline().decode('ASCII')
        return float(t)

    def GetAllTemps(self):

        t0 = read_command(self.ser, "IN_PV_13\r")
        t1 = read_command(self.ser, "IN_PV_03\r")

        if None in [t0, t1]:
            logging.info('No values!')
        else:
            return t0, t1

    def close(self):
        self.ser.close()
