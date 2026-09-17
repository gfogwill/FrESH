"""Chiller drivers.

The two lab PCs differ mainly in which chiller is attached, so the model is
read from the machine configuration (see :mod:`src.config`) and the matching
driver is built by :func:`make_chiller`.

``LAUDARP1845`` and ``LAUDARE1050`` speak the same serial protocol and used to
be two near-identical copies of the same code; they now share
:class:`LaudaSerial` and differ only in where the RTD probes are read from.
"""

import logging
import threading
import time

import serial
import serial.tools.list_ports

from src.daq.ADAMlib import ADAMConnection, ADAM4015

# LAUDA serial commands (see the "interface commands" table in the manual).
CMD_BATH_TEMP = "IN_PV_00\r"        # bath (outflow) temperature
CMD_SETPOINT = "IN_SP_00\r"         # temperature setpoint
CMD_CONTROLLED_TEMP = "IN_PV_01\r"  # controlled temperature indication
CMD_CUTOFF_POINT = "IN_SP_03\r"     # current overtemperature switch-off point
CMD_BATH_TEMP_MILLI = "IN_PV_10\r"  # bath temperature in 0.001 degC
CMD_SETPOINT_OFFSET = "IN_PAR_14\r"  # setpoint offset
CMD_MAX_OUTFLOW = "IN_PAR_09\r"     # maximum outflow temperature limit
CMD_EXT_TEMP_0 = "IN_PV_13\r"
CMD_EXT_TEMP_1 = "IN_PV_03\r"
# Formatted with the value as-is, exactly as the previous code did, so the
# chiller sees the same string it has always seen.
CMD_SET_SETPOINT = "OUT_SP_00_{}\r"


def read_command(connection, command: str):
    """Send ``command`` and return the reply as a float, or None if unparsable."""
    connection.write(command.encode('ASCII'))
    result = connection.readline()
    try:
        return float(result.decode('ASCII'))
    except (ValueError, TypeError, UnicodeDecodeError):
        return None


def find_usb_port():
    """Return the device name of the first USB serial port, or None."""
    for port in serial.tools.list_ports.comports():
        if 'USB' in port.description or 'USB' in (port.hwid or ''):
            return port.device
    return None


class LaudaSerial:
    """A LAUDA chiller on a serial port.

    All serial access goes through ``self._lock``: the readings are polled from
    the :class:`~src.gui.threads.DataWorker` thread while the setpoint is
    written from the GUI thread, and interleaving the two corrupts both.
    """

    MODEL = 'LAUDA'
    #: Pause after writing a new setpoint. This runs on the GUI thread, so
    #: keep it short; it used to be a full second, which froze the window on
    #: every step of a ramp.
    SET_TEMP_PAUSE = 0.05

    def __init__(self, config=None):
        self.config = config
        self.ser = None
        self.port = None
        self.connected = False
        self._lock = threading.RLock()

    # -- connection ----------------------------------------------------------

    def connect(self):
        """Open the chiller (and any extra hardware). Returns True on success."""
        try:
            self._connect_extra_hardware()

            self.port = find_usb_port()
            if self.port is None:
                raise serial.SerialException("No USB serial port found")

            self.ser = serial.Serial(self.port, timeout=0.5)
            time.sleep(1)
            self.connected = True
            logging.info(f"Connected to {self.MODEL} on port {self.port}")
            return True

        except Exception as e:
            logging.error(f"Failed to connect to {self.MODEL}: {e}")
            self.connected = False
            return False

    def _connect_extra_hardware(self):
        """Hook for models that need more than the serial line (e.g. an ADAM)."""

    def close(self):
        with self._lock:
            if self.ser and self.connected:
                try:
                    self.ser.close()
                    logging.info(f"{self.MODEL} connection closed successfully")
                except Exception as e:
                    logging.error(f"Error closing connection: {e}")
            self.connected = False

    # -- reading -------------------------------------------------------------

    def read_all_temp(self):
        """Return (bt, sp, t1, t2, temp, rh, t5), or a tuple of None on error."""
        if not self.connected:
            return (None,) * 7

        try:
            with self._lock:
                values = tuple(read_command(self.ser, cmd) for cmd in (
                    CMD_BATH_TEMP, CMD_SETPOINT, CMD_CONTROLLED_TEMP, CMD_CUTOFF_POINT,
                    CMD_BATH_TEMP_MILLI, CMD_SETPOINT_OFFSET, CMD_MAX_OUTFLOW))

            if None in values:
                raise ValueError("One or more temperature readings returned None")

            return values

        except Exception as e:
            logging.error(f"Error reading temperatures: {e}")
            return (None,) * 7

    def GetAllTemps(self):
        """Return the two RTD probe readings (RTD0, RTD1)."""
        if not self.connected:
            return None, None

        try:
            temps = self._read_rtds()
            if None in temps:
                raise ValueError("Invalid temperature readings")
            return temps
        except Exception as e:
            logging.error(f"Error reading RTD temperatures: {e}")
            return None, None

    def _read_rtds(self):
        """Read the two RTD probes. Overridden by models with an ADAM module."""
        with self._lock:
            return (read_command(self.ser, CMD_EXT_TEMP_0),
                    read_command(self.ser, CMD_EXT_TEMP_1))

    def get_data(self):
        """Return a dict of all current readings, or None if anything failed."""
        if not self.connected:
            logging.error("Device not connected. Please connect first.")
            return None

        try:
            s0, s1 = self.GetAllTemps()
            if None in (s0, s1):
                raise ValueError("Invalid RTD readings")

            bt, sp, t1, t2, temp, rh, t5 = self.read_all_temp()
            if None in (bt, sp, t1, t2, temp, rh, t5):
                raise ValueError("Invalid chiller readings")

            return {'BT': bt, 'SP': sp, 'RTD0': s0, 'RTD1': s1,
                    't1': t1, 't2': t2, 'TEMP': temp, 'RH': rh, 't5': t5}

        except Exception as e:
            logging.error(f"Error reading data from {self.MODEL}: {e}")
            return None

    # -- writing -------------------------------------------------------------

    def set_temperature(self, t_target):
        """Write a new setpoint. Returns True when the chiller acknowledges it."""
        if not self.connected:
            logging.error("Device not connected. Please connect first.")
            return False

        try:
            with self._lock:
                self.ser.write(CMD_SET_SETPOINT.format(t_target).encode('ASCII'))
                reply = self.ser.readline()

            if reply.strip() == b'OK':
                if self.SET_TEMP_PAUSE:
                    time.sleep(self.SET_TEMP_PAUSE)
                logging.info(f"Temperature set to {t_target} degC")
                return True

            logging.warning(f"{self.MODEL} did not acknowledge setpoint {t_target} "
                            f"(replied {reply!r})")
            return False

        except Exception as e:
            logging.error(f"Error setting temperature: {e}")
            return False


class LAUDARP1845(LaudaSerial):
    """LAUDA RP1845 -- RTD probes are read from the chiller itself."""

    MODEL = 'RP1845'


class LAUDARE1050(LaudaSerial):
    """LAUDA RE1050 -- RTD probes are read through an ADAM 4015 module."""

    MODEL = 'RE1050'

    def __init__(self, config=None):
        super().__init__(config)
        self.adam = None

    def _connect_extra_hardware(self):
        logging.info("Connecting ADAM")
        conn = ADAMConnection(self.config['SERIAL'])
        self.adam = ADAM4015(conn, 0x24, chs_to_enable=[0, 1])
        logging.info("ADAM Connected")

    def _read_rtds(self):
        return self.adam.GetAllTemps()


class LAUDARK20(LaudaSerial):
    """LAUDA RK20 -- deprecated, driven through an MCC DAQ board.

    Kept so old installations keep working; it needs the ``uldaq`` library.
    """

    MODEL = 'RK20'

    def __init__(self, config=None, init_temp=0):
        super().__init__(config)
        self.init_temp = init_temp
        self.adam = None
        self.daq = None

    def connect(self):
        try:
            from src.daq import mccdaq  # imported lazily: needs the uldaq library

            logging.info("Connecting ADAM")
            conn = ADAMConnection(self.config['SERIAL'])
            self.adam = ADAM4015(conn, 0x24, chs_to_enable=[0, 1])
            logging.info("ADAM Connected")

            logging.info("Connecting MC-DAQ")
            self.daq = mccdaq.Daq()
            self.daq.set_starting_temp(self.init_temp)
            logging.info("MC-DAQ Connected")

            self.connected = True
            return True
        except Exception as e:
            logging.error(f"Failed to connect to LAUDA RK20: {e}")
            self.connected = False
            return False

    def _read_rtds(self):
        return self.adam.GetAllTemps()

    def read_all_temp(self):
        try:
            return self.daq.read_all_temp()
        except Exception as e:
            logging.error(f"Error reading temperatures: {e}")
            return (None,) * 7

    def set_temperature(self, t_target):
        if not self.connected:
            logging.error("Device not connected. Please connect first.")
            return False
        try:
            self.daq.set_temperature(t_target)
            logging.info(f"Temperature set to {t_target} degC")
            return True
        except Exception as e:
            logging.error(f"Error setting temperature: {e}")
            return False

    def close(self):
        try:
            if self.daq is not None:
                self.daq.daq_device.release()
        except Exception as e:
            logging.error(f"Error releasing the DAQ device: {e}")
        self.connected = False


#: Chiller model name (as written in the config) -> driver class.
CHILLERS = {
    'RK20': LAUDARK20,
    'RP1845': LAUDARP1845,
    'RE1050': LAUDARE1050,
}


def make_chiller(config):
    """Build the chiller driver for the model named in ``config``.

    Raises
    ------
    ValueError
        If the configured model has no driver.
    """
    model = config['CHILLER']['MODEL'].strip().upper()

    try:
        chiller_class = CHILLERS[model]
    except KeyError:
        raise ValueError(f"Unsupported chiller model: {model}. "
                         f"Supported: {', '.join(sorted(CHILLERS))}")

    logging.info(f"Using chiller driver: {chiller_class.__name__}")
    return chiller_class(config)
