import cv2
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal, QObject, QTimer, QEventLoop

from PyQt5 import QtTest

from src.daq.ADAMlib import ADAMConnection, ADAM4015
from src.daq import mccdaq
from src.daq.IniLoader import IniLoader

import json


def read_coefficients(filepath):
    """
    This function reads the coefficients from a JSON file and returns them as a dictionary.

    Parameters:
    filepath (str): The filepath to the JSON file containing the coefficients.

    Returns:
    dict: The coefficients stored in the JSON file.
    """
    with open(filepath, 'r') as json_file:
        co = json.load(json_file)
        return co


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

        self.temp_corr_coeffs = read_coefficients(paths.raw_data_path + 'thermometers_corr_coeffs_20230127.json')

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
        RTD0, RTD1 = self.adam.GetAllTemps()
        BT, SP, TC1, TC2, TC3, TC4, TC5 = self.daq.read_all_temp()

        data = {'BT': BT,
                'SP': SP,
                'RTD0': RTD0,
                'RTD1': RTD1,
                'TC1': TC1,
                'TC2': TC2,
                'TC3': TC3,
                'TC4': TC4,
                'TC5': TC5}

        data = self.apply_corr_coeffs(data)

        self.read_data_signal.emit(data)

    def apply_corr_coeffs(self, data):
        for val in data:
            data[val] = data[val] * self.temp_corr_coeffs[val][0] + self.temp_corr_coeffs[val][1]

        return data


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
                self.change_pixmap_signal.emit(cv_img)

        # shut down capture system
        self.cap.release()

    def stop(self):
        """
        Sets run flag to False and waits for thread to finish
        """

        self._run_flag = False
        self.wait()
