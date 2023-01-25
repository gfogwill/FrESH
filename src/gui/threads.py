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
        bt = self.get_bath_temp()
        sp = self.get_setpoint_temp()
        s0, s1 = self.adam.GetAllTemps()
        t1, t2, t3, t4, t5 = self.get_thermocouples_temps()

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

    def get_bath_temp(self, samples=100, interval=1):
        """
        Get the bath temperature by reading from the DAQ.

        Parameters
        ----------
        samples : int, optional
            number of samples to collect (defaults to 100)
        interval : int, optional
            interval (in milliseconds) between samples (defaults to 1)

        Returns
        -------
        float
            the average over samples of the bath temperature in degrees Celsius
        """

        tmp = []

        for i in range(samples):
            QtTest.QTest.qWait(interval)
            a_in = self.daq.read_bath_temp()

            tmp.append(a_in)

        return sum(tmp) / len(tmp)

    def get_setpoint_temp(self, samples: int = 100, interval: int = 1) -> float:
        """
        Get the setpoint temperature by reading from the DAQ.

        Parameters
        ----------
        samples : int, optional
            number of samples to collect (defaults to 100)
        interval : int, optional
            interval (in milliseconds) between samples (defaults to 1)

        Returns
        -------
        float
            the average setpoint temperature in degrees Celsius

        Example
        -------
        >>>daq = SomeDAQ()
        >>>setpoint_temp = daq.get_setpoint_temp(samples = 50, interval = 2)
        >>>print(setpoint_temp)
        """
        tmp = []

        for i in range(samples):
            QtTest.QTest.qWait(interval)
            a_in = self.daq.read_setpoint_temp()

            tmp.append(a_in)

        return sum(tmp) / len(tmp)

    def get_thermocouples_temps(self, samples: int = 100, interval: int = 1) -> tuple[
        float | Any, float | Any, float | Any, float | Any, float | Any]:
        """
        Get the setpoint temperature by reading from the DAQ.

        Parameters
        ----------
        samples : int, optional
            number of samples to collect (defaults to 100)
        interval : int, optional
            interval (in milliseconds) between samples (defaults to 1)

        Returns
        -------
        float
            the average setpoint temperature in degrees Celsius

        Example
        -------
        >>>daq = SomeDAQ()
        >>>setpoint_temp = daq.get_setpoint_temp(samples = 50, interval = 2)
        >>>print(setpoint_temp)
        """
        tmp1 = []
        tmp2 = []
        tmp3 = []
        tmp4 = []
        tmp5 = []

        for i in range(samples):
            QtTest.QTest.qWait(interval)
            t1, t2, t3, t4, t5 = self.daq.read_thermocouples_temp()

            tmp1.append(t1)
            tmp2.append(t2)
            tmp3.append(t3)
            tmp4.append(t4)
            tmp5.append(t4)

        return sum(tmp1) / len(tmp1), sum(tmp2) / len(tmp2), sum(tmp3) / len(tmp3), sum(tmp4) / len(tmp4), sum(tmp5) / len(tmp5)


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
            cv_img = cv2.rotate(cv_img, cv2.ROTATE_180)

            if ret:
                # if get_circles:
                    # cv_img = get_circles(cv_img, self.plot_circles)
                    # pass

                self.change_pixmap_signal.emit(cv_img)

        # shut down capture system
        self.cap.release()

    def stop(self):
        """
        Sets run flag to False and waits for thread to finish
        """

        self._run_flag = False
        self.wait()
