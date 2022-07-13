#!/usr/bin/env python3

import sys
import time
import cv2
import logging
import os

import numpy as np
import pyqtgraph as pg

import PyQt5
from PyQt5 import QtGui, QtWidgets, uic, QtCore
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import QTimer, pyqtSlot, Qt, QObject, pyqtSignal, QThread
from PyQt5.QtWidgets import *

from src import paths

from src.daq import mccdaq
from src.gui.video import VideoThread
from src.daq.ADAMlib import ADAMConnection, ADAM4015
from src.daq.IniLoader import IniLoader

VIDEO_DISPLAY_WIDTH = 320
VIDEO_DISPLAY_HEIGHT = 240


class TimeAxisItem(pg.AxisItem):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setLabel(text='Time', units=None)
        self.enableAutoSIPrefix(False)

    def tickStrings(self, values, scale, spacing):
        return [time.strftime("%H:%M:%S", time.localtime(value)) for value in values]


class Worker(QObject):
    finished = pyqtSignal()
    progress = pyqtSignal(int)

    def run(self):
        """Long-running task."""
        t = time.time()

        bt = self.daq.get_bath_temp()
        sp = self.daq.get_setpoint_temp()
        s0, s1 = self.adam.GetAllTemps()

        self.bath_temp.append((t, bt))
        self.setpoint.append((t, sp))
        self.adam0.append((t, s0))
        self.adam1.append((t, s1))

        self.thread.setpoint_temp_text = f'{sp:.2f}'
        self.thread.bath_temp_text = f'{bt:.2f}'
        self.thread.ADAMCH0_temp_text = f'{s0:.2f}'
        self.thread.ADAMCH1_temp_text = f'{s1:.2f}'

        if self.save_exp:
            with open(self.experiment_path / "sensors_data.csv", "a") as fo:
                fo.write(f'{time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t))},'
                         f'{sp:.2f},'
                         f'{bt:.2f},'
                         f'{s0:.2f},'
                         f'{s1:.2f}\n')

        self.finished.emit()


def convert_cv_qt(cv_img):
    """Convert from an opencv image to QPixmap"""
    rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb_image.shape
    bytes_per_line = ch * w
    convert_to_Qt_format = QtGui.QImage(rgb_image.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)
    p = convert_to_Qt_format.scaled(VIDEO_DISPLAY_WIDTH, VIDEO_DISPLAY_HEIGHT, Qt.KeepAspectRatio)

    return QPixmap.fromImage(p)


class ExperimentUi(QtWidgets.QMainWindow):
    def __init__(self, exp_metadata, *args, **kwargs):
        super(ExperimentUi, self).__init__(*args, **kwargs)

        uic.loadUi('experiment.ui', self)

        self.save_exp = exp_metadata['save_exp']

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

        # Connect buttons
        self.button_set_temp = self.findChild(QtWidgets.QPushButton, 'setTempButton')  # Find the button
        self.button_set_temp.clicked.connect(self.set_temp)

        self.btn_connect = self.findChild(QtWidgets.QPushButton, 'connectButton')
        self.btn_connect.clicked.connect(self.connect_system)

        self.btn_exit = self.findChild(QtWidgets.QPushButton, 'exitButton')
        self.btn_exit.clicked.connect(self.exit)

        self.btn_clear_plot = self.findChild(QtWidgets.QPushButton, 'clearPlotButton')
        # self.btn_clear_plot.clicked.connect(self.clear_plot)
        self.btn_clear_plot.clicked.connect(self.read_sensors_data)

        # Change xaxis in GraphWidget yo show time in format HH:MM:SS
        self.graphWidget.setAxisItems(axisItems={'bottom': TimeAxisItem(orientation='bottom')})

        self.timer = QTimer()
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.update_temp_plot)

        if self.save_exp:
            self.setup_saving(exp_metadata)

        self.show()

    def save_pic(self):
        fo = self.experiment_path / 'pics' / time.strftime("%Y%m%d%H%M%S.png", time.localtime())
        self.image_label.pixmap().save(str(fo))

    def setup_saving(self, exp_metadata):
        log_fmt = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)

        date_str = time.strftime('%Y%m%d%H%M', time.localtime())
        self.experiment_path = paths.raw_data_path / date_str
        os.mkdir(self.experiment_path)
        os.mkdir(self.experiment_path / 'pics')

        logging.basicConfig(level=logging.INFO,
                            format=log_fmt,
                            filename=self.experiment_path / f'EX{date_str}.log',
                            filemode='w')

        logging.info(f"Experiment directory created: {self.experiment_path}")

        with open(self.experiment_path / "sensors_data.csv", "a") as fo:
            fo.write(f'datetime, '
                     f'setpoint [ºC], '
                     f'bath temp [ºC], '
                     f'RTD0 [ºC], '
                     f'RTD1 [ºC]\n')

        logging.info(f'Sensors data file created: {self.experiment_path / "sensors_data.csv"}')
        desc = exp_metadata['exp_description']
        logging.info(f'Experiment description:\n\n{desc}\n\n')

        self.timer2 = QTimer()
        self.timer2.setInterval(exp_metadata['picture_saving_interval'] * 1000)
        self.timer2.timeout.connect(self.save_pic)
        self.timer2.start()

    def connect_system(self):
        logging.info("Connecting System")

        # Connect to ADAM-4015
        ini = IniLoader.load('perezfo', '../../notebooks/test.ini')
        conn = ADAMConnection(ini['SERIAL'])
        self.adam = ADAM4015(conn, 0x24, chs_to_enable=[0, 1])

        # Connect MC-DAQ (USB-1808) and set the initial temperature
        self.daq = mccdaq.Daq()
        self.daq.set_starting_temp(float(self.temp_set.text()))

        # Setup video widget
        self.createVideoWidget()

        logging.info("Systems connected")

        # Start the timer
        self.timer.start()

    def read_sensors_data(self):
        self.reading_thread = QThread()
        # Step 3: Create a worker object
        self.worker = Worker()
        # Step 4: Move worker to the thread
        self.worker.moveToThread(self.reading_thread)
        # Step 5: Connect signals and slots
        self.reading_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.reading_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.reading_thread.finished.connect(self.reading_thread.deleteLater)
        # self.worker.progress.connect(self.reportProgress)
        # Step 6: Start the thread
        self.reading_thread.start()

        # t = time.time()
        #
        # bt = self.daq.get_bath_temp()
        # sp = self.daq.get_setpoint_temp()
        # s0, s1 = self.adam.GetAllTemps()
        #
        # self.bath_temp.append((t, bt))
        # self.setpoint.append((t, sp))
        # self.adam0.append((t, s0))
        # self.adam1.append((t, s1))
        #
        # self.thread.setpoint_temp_text = f'{sp:.2f}'
        # self.thread.bath_temp_text = f'{bt:.2f}'
        # self.thread.ADAMCH0_temp_text = f'{s0:.2f}'
        # self.thread.ADAMCH1_temp_text = f'{s1:.2f}'
        #
        # if self.save_exp:
        #     with open(self.experiment_path / "sensors_data.csv", "a") as fo:
        #         fo.write(f'{time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t))},'
        #                  f'{sp:.2f},'
        #                  f'{bt:.2f},'
        #                  f'{s0:.2f},'
        #                  f'{s1:.2f}\n')

    def exit(self):
        self.timer.stop()
        try:
            self.daq.daq_device.release()
        except AttributeError:
            logging.warning("DAQ device not initialized")

        try:
            self.thread.stop()
        except AttributeError:
            logging.warning("Camera not initialized")

        sys.exit()

    def clear_plot(self):
        self.bath_temp = []
        self.setpoint = []
        self.adam0 = []
        self.adam1 = []

        self.graphWidget.clear()

        self.graphWidget.enableAutoRange(axis='y')
        self.graphWidget.setAutoVisible(y=True)

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

        self.line3 = self.graphWidget.plot(*zip(*self.adam0), name="ADAM_0", pen=pen3)
        self.line4 = self.graphWidget.plot(*zip(*self.adam1), name="ADAM_1", pen=pen4)

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
    window = ExperimentUi()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    log_fmt = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logging.basicConfig(level=logging.INFO, format=log_fmt)
    main()
