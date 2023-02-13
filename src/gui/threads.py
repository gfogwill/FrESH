from typing import Tuple, Any

import cv2
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal, QObject, QTimer, QEventLoop

from PyQt5 import QtTest

from src.daq.ADAMlib import ADAMConnection, ADAM4015
from src.daq import mccdaq
from src.daq.IniLoader import IniLoader
# from src.gui.video import get_circles


class DataWorker(QThread):
    #TODO: Doc

    read_data_signal = pyqtSignal(object)

    def __init__(self, init_temp=0):
        super().__init__()
        self.init_temp = init_temp
        self.adam = None
        self.daq = None
        self.threadactive = True

        self.dataCollectionTimer = QTimer()
        self.dataCollectionTimer.moveToThread(self)
        self.dataCollectionTimer.timeout.connect(self.read_temps)

    def run(self):
        # Connect to ADAM-4015
        ini = IniLoader.load('perezfo', '../../notebooks/test.ini')
        conn = ADAMConnection(ini['SERIAL'])
        self.adam = ADAM4015(conn, 0x24, chs_to_enable=[0, 1])

        # Connect MC-DAQ (USB-1808) and set the initial temperature
        self.daq = mccdaq.Daq()
        self.daq.set_starting_temp(self.init_temp)

        self.dataCollectionTimer.start(1000)
        loop = QEventLoop()
        loop.exec_()

    def read_temps(self):
        s0, s1 = self.adam.GetAllTemps()
        bt, sp, t1, t2, t3, t4, t5 = self.daq.read_all_temp()

        data = {'bt': bt,
                'sp': sp,
                's0': s0,
                's1': s1,
                't1': t1,
                't2': t2,
                't3': t3,
                't4': t4,
                't5': t5}

        self.read_data_signal.emit(data)


class TempThread(QThread):
    temp_signal = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.chilling = True
        self.last_sp = 10
        self.chill_temp_step = 0.1
        self.cool_temp_step = 1
        self.step_interval = 60  # in seconds

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
            if self.last_sp == -35.0:
                self.chilling = False
        else:
            self.last_sp += self.cool_temp_step
            self.last_sp = round(self.last_sp, 2)
            if self.last_sp == 10.0:
                self.chilling = True
        self.temp_signal.emit(self.last_sp)
        # self.daq.set_temperature(self.last_sp)


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
            cv_img = cv2.rotate(cv_img, cv2.ROTATE_90_COUNTERCLOCKWISE)

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
