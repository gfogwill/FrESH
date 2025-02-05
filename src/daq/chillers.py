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
        self.connected = False

    def connect(self):
        try:
            logging.info("Connecting ADAM")
            conn = ADAMConnection(self.ini['SERIAL'])
            self.adam = ADAM4015(conn, 0x24, chs_to_enable=[0, 1])
            logging.info("ADAM Connected")

            logging.info("Connecting MC-DAQ")
            self.daq = mccdaq.Daq()
            self.daq.set_starting_temp(self.init_temp)
            logging.info("MC-DAQ Connected")

            self.connected = True
            return True
        except Exception as e:
            logging.error(f"Failed to connect to LAUDA RK20: {str(e)}")
            self.connected = False
            return False

    def get_data(self):
        if not self.connected:
            logging.error("Device not connected. Please connect first.")
            return None

        try:
            s0, s1 = self.adam.GetAllTemps()
            bt, sp, t1, t2, temp, rh, t5 = self.daq.read_all_temp()

            # Validate readings
            all_values = [bt, sp, s0, s1, t1, t2, temp, rh, t5]
            if any(v is None for v in all_values):
                raise ValueError("One or more sensor readings returned None")

            data = {
                'BT': bt,
                'SP': sp,
                'RTD0': s0,
                'RTD1': s1,
                't1': t1,
                't2': t2,
                'TEMP': temp,
                'RH': rh,
                't5': t5
            }
            return data
        except Exception as e:
            logging.error(f"Error reading data from LAUDA RK20: {str(e)}")
            return None

    def set_temperature(self, t_target):
        if not self.connected:
            logging.error("Device not connected. Please connect first.")
            return False

        try:
            self.daq.set_temperature(t_target)
            logging.info(f"Temperature set to {t_target}°C")
            return True
        except Exception as e:
            logging.error(f"Error setting temperature: {str(e)}")
            return False


class LAUDARP1845:
    def __init__(self):
        self.ser = None
        self.port = None
        self.connected = False

    def connect(self):
        try:
            self.ports = serial.tools.list_ports.comports()
            port_found = False

            for port_no, description, address in self.ports:
                if 'USB' in description:
                    self.port = str(port_no)
                    port_found = True
                    break

            if not port_found:
                raise serial.SerialException("No USB serial port found")

            self.ser = serial.Serial(self.port, timeout=0.5)
            time.sleep(1)
            self.connected = True
            logging.info(f"Connected to LAUDA RP1845 on port {self.port}")
            return True

        except Exception as e:
            logging.error(f"Failed to connect to LAUDA RP1845: {str(e)}")
            self.connected = False
            return False

    def get_data(self):
        if not self.connected:
            logging.error("Device not connected. Please connect first.")
            return None

        try:
            s0, s1 = self.GetAllTemps()
            if None in (s0, s1):
                raise ValueError("Invalid temperature readings from GetAllTemps")

            bt, sp, t1, t2, temp, rh, t5 = self.read_all_temp()
            if None in (bt, sp, t1, t2, temp, rh, t5):
                raise ValueError("Invalid temperature readings from read_all_temp")

            data = {
                'BT': bt,
                'SP': sp,
                'RTD0': s0,
                'RTD1': s1,
                't1': t1,
                't2': t2,
                'TEMP': temp,
                'RH': rh,
                't5': t5
            }
            return data

        except Exception as e:
            logging.error(f"Error reading data from LAUDA RP1845: {str(e)}")
            return None

    def set_temperature(self, t_target):
        if not self.connected:
            logging.error("Device not connected. Please connect first.")
            return False

        try:
            self.ser.write(f"OUT_SP_00_{t_target}\r".encode('ASCII'))
            time.sleep(1)
            logging.info(f"Temperature set to {t_target}°C")
            return True
        except Exception as e:
            logging.error(f"Error setting temperature: {str(e)}")
            return False

    def read_all_temp(self):
        if not self.connected:
            return None, None, None, None, None, None, None

        try:
            # Read bath temperature (outflow temperature)
            bt = read_command(self.ser, "IN_PV_00\r")
            # Read temperature setpoint
            sp = read_command(self.ser, "IN_SP_00\r")
            # Controlled temperature indication
            t1 = read_command(self.ser, "IN_PV_01\r")
            # Current overtemperature switch-off point
            t2 = read_command(self.ser, "IN_SP_03\r")
            # Bath temperature in 0.001°C
            temp = read_command(self.ser, "IN_PV_10\r")
            # Setpoint offset
            rh = read_command(self.ser, "IN_PAR_14\r")
            # Maximum outflow temperature limit
            t5 = read_command(self.ser, "IN_PAR_09\r")

            if None in (bt, sp, t1, t2, temp, rh, t5):
                raise ValueError("One or more temperature readings returned None")

            return bt, sp, t1, t2, temp, rh, t5

        except Exception as e:
            logging.error(f"Error reading temperatures: {str(e)}")
            return None, None, None, None, None, None, None

    def GetAllTemps(self):
        if not self.connected:
            return None, None

        try:
            t0 = read_command(self.ser, "IN_PV_13\r")
            t1 = read_command(self.ser, "IN_PV_03\r")

            if None in (t0, t1):
                raise ValueError("Invalid temperature readings")

            return t0, t1

        except Exception as e:
            logging.error(f"Error reading temperatures: {str(e)}")
            return None, None

    def close(self):
        if self.ser and self.connected:
            try:
                self.ser.close()
                self.connected = False
                logging.info("Connection closed successfully")
            except Exception as e:
                logging.error(f"Error closing connection: {str(e)}")


class LAUDARE1050:
    def __init__(self):
        self.ser = None
        self.port = None
        self.connected = False

    def connect(self):
        try:
            self.ports = serial.tools.list_ports.comports()
            port_found = False

            for port_no, description, address in self.ports:
                if 'USB' in description:
                    self.port = str(port_no)
                    port_found = True
                    break

            if not port_found:
                raise serial.SerialException("No USB serial port found")

            self.ser = serial.Serial(self.port, timeout=0.5)
            time.sleep(1)
            self.connected = True
            logging.info(f"Connected to LAUDA RE1050 on port {self.port}")
            return True

        except Exception as e:
            logging.error(f"Failed to connect to LAUDA RE1050: {str(e)}")
            self.connected = False
            return False

    def get_data(self):
        if not self.connected:
            logging.error("Device not connected. Please connect first.")
            return None

        try:
            # s0, s1 = self.GetAllTemps()
            # if None in (s0, s1):
            #     raise ValueError("Invalid temperature readings from GetAllTemps")

            bt, sp, t1, t2, temp, rh, t5 = self.read_all_temp()
            if None in (bt, sp, t1, t2, temp, rh, t5):
                raise ValueError("Invalid temperature readings from read_all_temp")

            data = {
                'BT': bt,
                'SP': sp,
#                'RTD0': s0,
#                'RTD1': s1,
                't1': t1,
                't2': t2,
                'TEMP': temp,
                'RH': rh,
                't5': t5
            }
            return data

        except Exception as e:
            logging.error(f"Error reading data from LAUDA RE1050: {str(e)}")
            return None

    def set_temperature(self, t_target):
        if not self.connected:
            logging.error("Device not connected. Please connect first.")
            return False

        try:
            self.ser.write(f"OUT_SP_00_{t_target}\r".encode('ASCII'))
            time.sleep(1)
            logging.info(f"Temperature set to {t_target}°C")
            return True
        except Exception as e:
            logging.error(f"Error setting temperature: {str(e)}")
            return False

    def read_all_temp(self):
        if not self.connected:
            return None, None, None, None, None, None, None

        try:
            # Read bath temperature (outflow temperature)
            bt = read_command(self.ser, "IN_PV_00\r")
            # Read temperature setpoint
            sp = read_command(self.ser, "IN_SP_00\r")
            # Controlled temperature indication
            t1 = read_command(self.ser, "IN_PV_01\r")
            # Current overtemperature switch-off point
            t2 = read_command(self.ser, "IN_SP_03\r")
            # Bath temperature in 0.001°C
            temp = read_command(self.ser, "IN_PV_10\r")
            # Setpoint offset
            rh = read_command(self.ser, "IN_PAR_14\r")
            # Maximum outflow temperature limit
            t5 = read_command(self.ser, "IN_PAR_09\r")

            if None in (bt, sp, t1, t2, temp, rh, t5):
                raise ValueError("One or more temperature readings returned None")

            return bt, sp, t1, t2, temp, rh, t5

        except Exception as e:
            logging.error(f"Error reading temperatures: {str(e)}")
            return None, None, None, None, None, None, None

    def GetAllTemps(self):
        if not self.connected:
            return None, None

        try:
            t0 = read_command(self.ser, "IN_PV_13\r")
            t1 = read_command(self.ser, "IN_PV_03\r")

            if None in (t0, t1):
                raise ValueError("Invalid temperature readings")

            return t0, t1

        except Exception as e:
            logging.error(f"Error reading temperatures: {str(e)}")
            return None, None

    def close(self):
        if self.ser and self.connected:
            try:
                self.ser.close()
                self.connected = False
                logging.info("Connection closed successfully")
            except Exception as e:
                logging.error(f"Error closing connection: {str(e)}")