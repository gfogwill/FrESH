import sys
import time
import cv2
import logging

import numpy as np
import pyqtgraph as pg

from PyQt5 import QtGui, QtWidgets, uic
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import QTimer, pyqtSlot, Qt
from PyQt5.QtWidgets import *

from src import paths

from src.daq import mccdaq
from src.gui.video import VideoThread
from src.daq.ADAMlib import ADAMConnection, ADAM4015
from src.daq.IniLoader import IniLoader

VIDEO_DISPLAY_WIDTH = 640
VIDEO_DISPLAY_HEIGHT = 480


class TimeAxisItem(pg.AxisItem):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setLabel(text='Time', units=None)
        self.enableAutoSIPrefix(False)

    def tickStrings(self, values, scale, spacing):
        return [time.strftime("%H:%M:%S", time.localtime(value)) for value in values]


def convert_cv_qt(cv_img):
    """Convert from an opencv image to QPixmap"""
    rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb_image.shape
    bytes_per_line = ch * w
    convert_to_Qt_format = QtGui.QImage(rgb_image.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)
    p = convert_to_Qt_format.scaled(VIDEO_DISPLAY_WIDTH, VIDEO_DISPLAY_HEIGHT, Qt.KeepAspectRatio)

    return QPixmap.fromImage(p)


class Ui(QtWidgets.QMainWindow):
    def __init__(self, *args, **kwargs):
        super(Ui, self).__init__(*args, **kwargs)

        uic.loadUi('test.ui', self)

        self.bath_temp = []
        self.setpoint = []
        self.adam0 = []
        self.adam1 = []

        self.line1 = None
        self.line2 = None
        self.line3 = None
        self.line4 = None

        self.daq = None
        self.adam = None
        self.thread = None
        self.image_label = None

        # Setup video widget
        self.createVideoWidget()

        # Connect buttons
        self.button_set_temp = self.findChild(QtWidgets.QPushButton, 'setTempButton')  # Find the button
        self.button_set_temp.clicked.connect(self.set_temp)

        self.btn_connect = self.findChild(QtWidgets.QPushButton, 'connectButton')
        self.btn_connect.clicked.connect(self.connect_system)

        self.btn_exit = self.findChild(QtWidgets.QPushButton, 'exitButton')
        self.btn_exit.clicked.connect(self.exit)

        self.btn_clear_plot = self.findChild(QtWidgets.QPushButton, 'clearPlotButton')
        self.btn_clear_plot.clicked.connect(self.clear_plot)

        # Change xaxis in GraphWidget yo show time in format HH:MM:SS
        self.graphWidget.setAxisItems(axisItems={'bottom': TimeAxisItem(orientation='bottom')})

        self.timer = QTimer()
        self.timer.setInterval(1)
        self.timer.timeout.connect(self.update_temp_plot)

        self.show()

    def connect_system(self):
        logging.info("Connecting System")

        # Connect to ADAM-4015
        #ini = IniLoader.load('perezfo', '../../notebooks/test.ini')
        #conn = ADAMConnection(ini['SERIAL'])
        #self.adam = ADAM4015(conn, 0x0A, chs_to_enable=[0, 1])

        # Connect MC-DAQ (USB-1808) and set the initial temperature
        self.daq = mccdaq.Daq()
        self.daq.set_starting_temp(float(self.temp_set.text()))

        # Start the timer
        self.timer.start()

    def read_sensors_data(self):
        t = time.time()

        self.bath_temp.append((t, self.daq.get_bath_temp(samples=self.samplesHorizontalSlider.value(), interval=self.intervalHorizontalSlider.value()*1e-3)))
        self.setpoint.append((t, self.daq.get_setpoint_temp(samples=self.samplesHorizontalSlider.value(), interval=self.intervalHorizontalSlider.value()*1e-3)))
        #self.adam0.append((t, self.adam.GetTemp(ch=0)))
        #self.adam1.append((t, self.adam.GetTemp(ch=1)))

        self.thread.setpoint_temp_text = f'{(self.setpoint[-1][1]):.2f}'
        self.thread.bath_temp_text = f'{(self.bath_temp[-1][1]):.2f}'
        #self.thread.ADAMCH0_temp_text = f'{(self.adam0[-1][1]):.2f}'
        #self.thread.ADAMCH1_temp_text = f'{(self.adam1[-1][1]):.2f}'

        self.setpoint_value.setText(f'{(self.setpoint[-1][1] / 100 * 1e3):.3f} mV')
        self.bath_temp_value.setText(f'{(self.bath_temp[-1][1] / 100 * 1e3):.3f} mV')

    def exit(self):
        self.timer.stop()
        try:
            self.daq.daq_device.release()
        except AttributeError:
            logging.error("DAQ device not initialized")

        self.thread.stop()
        sys.exit()

    def clear_plot(self):
        self.bath_temp = []
        self.setpoint = []
        self.adam0 = []
        self.adam1 = []

        self.graphWidget.clear()

    def createVideoWidget(self):
        self.image_label = self.findChild(QtWidgets.QLabel, 'videoLabel')
        self.thread = VideoThread()
        # connect its signal to the update_image slot
        self.thread.change_pixmap_signal.connect(self.update_image)
        # start the thread
        self.thread.start()

    def update_temp_plot(self):

        self.read_sensors_data()

        pen = pg.mkPen(color='red', width=1)
        pen2 = pg.mkPen(color='green', width=1)
        pen3 = pg.mkPen(color='blue', width=1)
        pen4 = pg.mkPen(color='orange', width=1)

        self.graphWidget.setLabel('left', 'Bath temp [ºC]', color='red', size=30)
        self.graphWidget.setLabel('right', 'Setpoint temp [ºC]', color='green', size=30)
        self.graphWidget.setLabel('bottom', 'Time', size=30)

        self.line1 = self.graphWidget.plot(*zip(*self.bath_temp), name="Bath temp.", pen=pen)
        self.line2 = self.graphWidget.plot(*zip(*self.setpoint), name="Setpoint temp.", pen=pen2)

        #self.line3 = self.graphWidget.plot(*zip(*self.adam0), name="ADAM_0", pen=pen3)
        #self.line4 = self.graphWidget.plot(*zip(*self.adam1), name="ADAM_1", pen=pen4)

    def set_temp(self):
        t = float(self.temp_set.text())
        logging.info(f'Setting temperature to: {t}')
        self.daq.set_temperature(t)

    @pyqtSlot(np.ndarray)
    def update_image(self, cv_img):
        """Updates the image_label with a new opencv image"""
        qt_img = convert_cv_qt(cv_img)
        self.image_label.setPixmap(qt_img)


def main():
    app = QtWidgets.QApplication(sys.argv)
    window = Ui()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    log_fmt = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logging.basicConfig(level=logging.INFO, format=log_fmt)
    main()
