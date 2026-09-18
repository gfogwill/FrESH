"""Background workers: chiller I/O and the camera.

The temperature ramp used to live here as a QThread. It is now
:class:`src.experiment.series.SeriesController`, which runs on the GUI
thread: it only does arithmetic, and keeping it out of a thread means it
can read the latest chiller reading without any locking.
"""

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
        """Poll the chiller and emit the readings.

        A failed read emits ``None`` rather than emitting nothing: a running
        freeze/thaw series counts those to decide the chiller has stopped
        answering, and it can only count what it is told about.
        """
        if not self.threadactive:
            return

        data = None
        try:
            if not self.connected:
                logging.error("Cannot read temperatures - device not connected")
            else:
                data = self.chiller.get_data()
                if data is None:
                    logging.warning("No valid data received from chiller")
        except Exception as e:
            logging.error(f"Error reading temperatures: {e}")

        self.read_data_signal.emit(data)

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
