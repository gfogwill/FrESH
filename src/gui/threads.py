import cv2
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal, QObject, QTimer, QEventLoop

from src.daq.ADAMlib import ADAMConnection, ADAM4015
from src.daq import mccdaq
from src.daq.IniLoader import IniLoader
from src.gui.video import get_circles


def get_circles(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    img_blur = cv2.medianBlur(gray, 5)

    circles = cv2.HoughCircles(img_blur,
                               cv2.HOUGH_GRADIENT,
                               1,
                               minDist=25,  # img.shape[0] / 20,
                               param1=200,
                               param2=10,
                               minRadius=10,
                               maxRadius=15,
                               )

    # Draw detected circles
    if circles is not None:
        circles = np.uint16(np.around(circles))
        for i in circles[0, :96]:
            # outer circle
            # cv2.circle(image, center_coordinates, radius, color, thickness)
            cv2.circle(img, (i[0], i[1]), i[2], (0, 0, 0), 1)

            # inner circle
            #cv2.circle(img, (i[0], i[1]), 1, (0, 0, 255), 2)

    return img


class DataWorker(QThread):

    read_data_signal = pyqtSignal(object)

    def __init__(self, init_temp=15):
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
        bt = self.daq.get_bath_temp()
        sp = self.daq.get_setpoint_temp()
        s0, s1 = self.adam.GetAllTemps()

        data = {'bath_temp': bt,
                'setpoint_temp': sp,
                'adam0': s0,
                'adam1': s1}

        self.read_data_signal.emit(data)


class VideoThread(QThread):
    change_pixmap_signal = pyqtSignal(np.ndarray)

    bath_temp_text = '-'
    setpoint_temp_text = '-'
    ADAMCH0_temp_text = '-'
    ADAMCH1_temp_text = '-'

    detect_circles = False

    def __init__(self):
        super().__init__()
        self._run_flag = True
        # capture from webcam
        self.cap = cv2.VideoCapture(3)

    def run(self):

        while self._run_flag:
            ret, cv_img = self.cap.read()

            if ret:
                cv2.putText(cv_img, f"     Bath temp: {self.bath_temp_text}",
                            (50, 50), cv2.FONT_HERSHEY_PLAIN, 1, (0, 255, 0), 1)
                cv2.putText(cv_img, f" Setpoint temp: {self.setpoint_temp_text}",
                            (50, 70), cv2.FONT_HERSHEY_PLAIN, 1, (0, 255, 0), 1)
                cv2.putText(cv_img, f"ADAM CH1 temp: {self.ADAMCH0_temp_text}",
                            (50, 90), cv2.FONT_HERSHEY_PLAIN, 1, (0, 255, 0), 1)
                cv2.putText(cv_img, f"ADAM CH2 temp: {self.ADAMCH1_temp_text}",
                            (50, 110), cv2.FONT_HERSHEY_PLAIN, 1, (0, 255, 0), 1)

                if get_circles:
                    cv_img = get_circles(cv_img)

                self.change_pixmap_signal.emit(cv_img)

        # shut down capture system
        self.cap.release()

    def stop(self):
        """Sets run flag to False and waits for thread to finish"""
        self._run_flag = False
        self.wait()
