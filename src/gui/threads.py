"""Background workers: chiller I/O, the temperature ramp and the camera."""

import logging
import time

import cv2
import numpy as np

from PyQt6.QtCore import QThread, QTimer, pyqtSignal

from src.config import get_config
from src.daq.chillers import make_chiller


class DataWorker(QThread):
    """Polls the chiller once a second and emits the readings."""

    read_data_signal = pyqtSignal(object)
    connection_status_signal = pyqtSignal(bool)

    #: Polling period, in milliseconds.
    POLL_INTERVAL_MS = 1000

    def __init__(self, init_temp=0):
        super().__init__()

        self.init_temp = init_temp
        self.threadactive = True
        self.connected = False

        try:
            self.chiller = make_chiller(get_config())
        except Exception as e:
            logging.error(f"Error initializing chiller: {e}")
            self.chiller = None

        self.dataCollectionTimer = QTimer()
        self.dataCollectionTimer.moveToThread(self)
        self.dataCollectionTimer.timeout.connect(self.read_temps)

    def run(self):
        if self.chiller is None:
            logging.error("Chiller not initialized properly")
            self.connection_status_signal.emit(False)
            return

        try:
            if not self.chiller.connect():
                logging.error("Failed to connect to chiller")
                self.connection_status_signal.emit(False)
                return

            self.connected = True
            self.connection_status_signal.emit(True)
            logging.info("Chiller connected successfully")

            self.dataCollectionTimer.start(self.POLL_INTERVAL_MS)
            # QThread's own event loop, so that stop() -> quit() actually ends it.
            self.exec()
        except Exception as e:
            logging.error(f"Error in chiller thread: {e}")
            self.connection_status_signal.emit(False)
        finally:
            self.dataCollectionTimer.stop()

    def read_temps(self):
        if not self.threadactive:
            return

        try:
            if not self.connected:
                logging.error("Cannot read temperatures - device not connected")
                return

            data = self.chiller.get_data()
            if data is not None:
                self.read_data_signal.emit(data)
            else:
                logging.warning("No valid data received from chiller")

        except Exception as e:
            logging.error(f"Error reading temperatures: {e}")

    def set_temperature(self, t_target):
        """Write a setpoint, if the chiller is up."""
        if self.chiller is None or not self.connected:
            logging.error("Cannot set temperature - chiller not connected")
            return False
        return self.chiller.set_temperature(t_target)

    def stop(self):
        """Stop polling, end the thread and close the chiller connection."""
        self.threadactive = False
        self.quit()
        if not self.wait(3000):
            logging.warning("Chiller thread did not stop in time")

        self.connected = False
        if self.chiller is not None and hasattr(self.chiller, 'close'):
            try:
                self.chiller.close()
            except Exception as e:
                logging.error(f"Error closing chiller connection: {e}")


class TempThread(QThread):
    """Ramps the chiller setpoint down to ``min_temp`` and back up again.

    The rates are given in degC/min, as they are labelled in the GUI; the ramp
    itself moves in steps of ``step_interval`` seconds.
    """

    temp_signal = pyqtSignal(object)

    #: Seconds between setpoint steps.
    STEP_INTERVAL = 6

    def __init__(self, max_temp, min_temp, cooling_rate, heating_rate,
                 cycles=None, step_interval=STEP_INTERVAL):
        super().__init__()

        if max_temp <= min_temp:
            raise ValueError(f"Max. temp ({max_temp}) must be above min. temp ({min_temp})")

        self.max_temp = max_temp
        self.min_temp = min_temp
        self.step_interval = step_interval

        # degC per step, from the degC/min entered in the GUI.
        self.chill_temp_step = abs(cooling_rate) * step_interval / 60.0
        self.heat_temp_step = abs(heating_rate) * step_interval / 60.0

        if not self.chill_temp_step or not self.heat_temp_step:
            raise ValueError("Cooling and heating rates must be greater than zero")

        #: None means "keep cycling until the operator stops the scan".
        self.cycles = cycles
        self.completed_cycles = 0

        self.chilling = True
        self.last_sp = max_temp

        self.tempRampTimer = QTimer()
        self.tempRampTimer.moveToThread(self)
        self.tempRampTimer.timeout.connect(self.update_temp)

    def run(self):
        self.tempRampTimer.start(int(self.step_interval * 1000))
        self.exec()
        self.tempRampTimer.stop()

    def update_temp(self):
        """Advance the setpoint one step, turning around at the limits.

        The limits used to end the scan: overshooting min_temp by any amount
        emitted a setpoint of 0 and killed the thread, so unless the span was an
        exact multiple of the step the heating ramp never ran at all. Now the
        setpoint is clamped to the limit and the ramp reverses.
        """
        if self.chilling:
            next_sp = self.last_sp - self.chill_temp_step
            if next_sp <= self.min_temp:
                next_sp = self.min_temp
                self.chilling = False
                logging.info(f"Minimum temperature ({self.min_temp} degC) reached, heating up")
        else:
            next_sp = self.last_sp + self.heat_temp_step
            if next_sp >= self.max_temp:
                next_sp = self.max_temp
                self.chilling = True
                self.completed_cycles += 1
                logging.info(f"Maximum temperature ({self.max_temp} degC) reached, "
                             f"cycle {self.completed_cycles} complete")

        self.last_sp = round(next_sp, 2)
        self.temp_signal.emit(self.last_sp)

        if self.cycles is not None and self.completed_cycles >= self.cycles:
            logging.info(f"Requested {self.cycles} cycle(s) done, stopping the ramp")
            self.quit()

    def stop(self):
        """Ask the ramp to stop and wait for the thread to finish."""
        self.quit()
        if not self.wait(3000):
            logging.warning("Temperature ramp thread did not stop in time")


class VideoThread(QThread):
    """Captures frames from the camera and emits them as numpy arrays."""

    change_pixmap_signal = pyqtSignal(np.ndarray)

    def __init__(self, camera_ID):
        """
        Parameters
        ----------
        camera_ID : int
            ID of the camera to capture video from.
        """
        super().__init__()
        self._run_flag = True

        self.plot_circles = False
        self.detect_circles = False

        #: The most recent frame, for whoever needs to save a picture. Reading
        #: the capture from another thread races with run() and returns torn or
        #: duplicated frames, so grab this instead.
        self.last_frame = None

        self.cap = cv2.VideoCapture(camera_ID)
        if not self.cap.isOpened():
            logging.error(f"Could not open camera {camera_ID}")

    def run(self):
        while self._run_flag:
            ret, cv_img = self.cap.read()

            if ret:
                self.last_frame = cv_img
                self.change_pixmap_signal.emit(cv_img)
            else:
                # Do not spin at 100% CPU when the camera stops delivering.
                time.sleep(0.05)

        self.cap.release()

    def stop(self):
        """Sets run flag to False and waits for thread to finish."""
        self._run_flag = False
        if not self.wait(3000):
            logging.warning("Video thread did not stop in time")
