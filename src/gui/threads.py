import logging
from typing import Tuple, Any

import cv2
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal, QObject, QTimer, QEventLoop

from PyQt5 import QtTest

from src.daq.IniLoader import IniLoader
from src import paths
from src.daq import chillers


class DataWorker(QThread):

    read_data_signal = pyqtSignal(object)

    def __init__(self, init_temp=0):
        super().__init__()

        # Load ini file
        ini = IniLoader.load('perezfo', paths.etc_path / 'test.ini')

        if ini['CHILLER']['MODEL'] == 'RK20':
            self.chiller = chillers.LAUDARK20(ini)

        elif ini['CHILLER']['MODEL'] == 'RP1845':
            self.chiller = chillers.LAUDARP1845()

        self.threadactive = True

        self.dataCollectionTimer = QTimer()
        self.dataCollectionTimer.moveToThread(self)
        self.dataCollectionTimer.timeout.connect(self.read_temps)

    def run(self):
        self.chiller.connect()

        self.dataCollectionTimer.start(1000)
        loop = QEventLoop()
        loop.exec_()

    def read_temps(self):
        data = self.chiller.get_data()
        self.read_data_signal.emit(data)


class TempThread(QThread):
    temp_signal = pyqtSignal(float)

    def __init__(self, max_temp, min_temp, cooling_rate, heating_rate, cycles=1, target_temp=None):
        super().__init__()
        self.max_temp = max_temp
        self.min_temp = min_temp
        self.cooling_rate = cooling_rate
        self.heating_rate = heating_rate
        self.cycles = cycles
        self.target_temp = target_temp
        self.stopped = False

    def run(self):
        for cycle in range(self.cycles):
            if self.stopped:
                break

            if self.target_temp is not None:
                self.go_to_target_temp(self.target_temp)
                self.stay_at_target_temp()
            else:
                self.cool_to_min()
                self.heat_to_max()

    def go_to_target_temp(self, target_temp):
        current_temp = self.max_temp if self.cooling_rate > 0 else self.min_temp

        while not self.stopped:
            if self.cooling_rate > 0 and current_temp <= target_temp:
                break
            elif self.heating_rate > 0 and current_temp >= target_temp:
                break

            current_temp += -self.cooling_rate if self.cooling_rate > 0 else self.heating_rate
            self.temp_signal.emit(current_temp)
            time.sleep(1)

    def stay_at_target_temp(self):
        # Implement any additional logic if needed
        pass

    def cool_to_min(self):
        current_temp = self.max_temp
        while current_temp > self.min_temp and not self.stopped:
            current_temp -= self.cooling_rate
            self.temp_signal.emit(current_temp)

    def heat_to_max(self):
        current_temp = self.min_temp
        while current_temp < self.max_temp and not self.stopped:
            current_temp += self.heating_rate
            self.temp_signal.emit(current_temp)


class TempThread_deprecated(QThread):
    temp_signal = pyqtSignal(object)

    def __init__(self, max_temp, min_temp, cooling_rate, heating_rate):
        super().__init__()
        self.chilling = True
        self.last_sp = max_temp

        self.max_temp = max_temp
        self.min_temp = min_temp

        self.chill_temp_step = cooling_rate
        self.heat_temp_step = heating_rate
        self.step_interval = 6  # in seconds

        self.tempRampTimer = QTimer()
        self.tempRampTimer.moveToThread(self)
        self.tempRampTimer.timeout.connect(self.update_temp)

    def run(self):
        self.tempRampTimer.start(int(self.step_interval / 1e-3))
        loop = QEventLoop()
        loop.exec_()

    def update_temp(self):

        if self.chilling:
            self.last_sp -= self.chill_temp_step
            self.last_sp = round(self.last_sp, 2)
            if self.last_sp <= self.min_temp:
                self.chilling = False
        else:
            self.last_sp += self.heat_temp_step
            self.last_sp = round(self.last_sp, 2)
            if self.last_sp >= self.max_temp:
                self.chilling = True

        if self.last_sp < self.min_temp:
            logging.warning("Temperature below minimum limit. Setting to minimum.")
            self.last_sp = self.min_temp
            self.temp_signal.emit(0)
            self.terminate()

        if self.last_sp > self.max_temp:
            logging.warning("Temperature above maximum limit. Setting to maximum.")
            self.last_sp = self.max_temp
            self.temp_signal.emit(0)
            self.terminate()

        self.temp_signal.emit(self.last_sp)


class VideoThread(QThread):
    """
        Subclass of QThread for capturing video from a webcam and emitting the frames as a numpy array.
    """
    change_pixmap_signal = pyqtSignal(np.ndarray)

    detect_circles = False

    def __init__(self, camera_ID):

        """
            Initialize the video thread.

            Parameters
            ----------
            camera_ID : int
                ID of the camera to capture video from.
            """
        super().__init__()
        self._run_flag = True

        self.plot_circles = False

        # capture from webcam
        self.cap = cv2.VideoCapture(camera_ID)

    def run(self):
        """
        Run method for the thread. Continuously captures video frames and emits them via the change_pixmap_signal.
        """

        while self._run_flag:

            ret, cv_img = self.cap.read()

            if ret:
                self.change_pixmap_signal.emit(cv_img)

        # shut down capture system
        self.cap.release()

    def stop(self):
        """
        Sets run flag to False and waits for thread to finish
        """

        self._run_flag = False
        self.wait()
