#!/usr/bin/env python3

import sys
import time
import cv2
import logging
import os
import json

import numpy as np
import pyqtgraph as pg

import PyQt5
from PyQt5 import QtGui, QtWidgets, uic, QtCore
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import QTimer, pyqtSlot, Qt
from PyQt5.QtWidgets import *

from src import paths, __version__

from src.gui.threads import VideoThread, DataWorker, TempThread
from src.gui.video import VideoSettingsUi

from src.daq import mccdaq
from src.daq.ADAMlib import ADAMConnection, ADAM4015
# from src.daq.IniLoader import IniLoader

VIDEO_DISPLAY_WIDTH = 525
VIDEO_DISPLAY_HEIGHT = 359

if hasattr(QtCore.Qt, 'AA_EnableHighDpiScaling'):
    PyQt5.QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)

if hasattr(QtCore.Qt, 'AA_UseHighDpiPixmaps'):
    PyQt5.QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)


def convert_cv_qt(cv_img):
    """Convert from an opencv image to QPixmap"""
    rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb_image.shape
    bytes_per_line = ch * w
    convert_to_Qt_format = QtGui.QImage(rgb_image.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)
    p = convert_to_Qt_format.scaled(VIDEO_DISPLAY_WIDTH, VIDEO_DISPLAY_HEIGHT, Qt.KeepAspectRatio)

    return QPixmap.fromImage(p)


class ExperimentUi(QtWidgets.QMainWindow):
    def __init__(self, exp_list, *args, **kwargs):
        super(ExperimentUi, self).__init__(*args, **kwargs)

        uic.loadUi(paths.src_module_dir / 'gui' / 'experiment.ui', self)

        self.exp_list = exp_list
        self.bath_temp = []
        self.setpoint = []
        self.adam0 = []
        self.adam1 = []
        self.TEMP = []
        self.RH = []

        self.new_line1 = None
        self.line2 = None
        self.line3 = None
        self.line4 = None

        self.video_thread = None
        self.image_frame = None

        # Connect buttons
        self.button_set_temp = self.findChild(QtWidgets.QPushButton, 'setTempButton')  # Find the button
        self.button_set_temp.clicked.connect(self.set_temp)

        self.btn_connect_video = self.findChild(QtWidgets.QPushButton, 'connectVideoButton')
        self.btn_connect_video.clicked.connect(self.connect_video)

        self.btn_connect_lauda = self.findChild(QtWidgets.QPushButton, 'connectLAUDAButton')
        self.btn_connect_lauda.clicked.connect(self.connect_chiller)

        self.btn_start_scan = self.findChild(QtWidgets.QPushButton, 'startScanButton')
        self.btn_start_scan.clicked.connect(self.start_scan)

        self.btn_exit = self.findChild(QtWidgets.QPushButton, 'exitButton')
        self.btn_exit.clicked.connect(self.exit)

        self.btn_clear_plot = self.findChild(QtWidgets.QPushButton, 'clearPlotButton')
        self.btn_clear_plot.clicked.connect(self.clear_data)

        self.btn_video_settings = self.findChild(QtWidgets.QPushButton, 'videoSettingsButton')
        self.btn_video_settings.clicked.connect(self.video_settings)

        # Change xaxis in GraphWidget yo show time in format HH:MM:SS
        self.graphWidget.setAxisItems(axisItems={'bottom': TimeAxisItem(orientation='bottom')})

        self.saveCheckBox.stateChanged.connect(self.setup_saving)

        # Create a custom logging handler
        self.log_text_edit = self.findChild(QtWidgets.QPlainTextEdit, 'logTextEdit')
        self.log_handler = QPlainTextEditLogger(self.log_text_edit)
        logging.getLogger().addHandler(self.log_handler)

        pen = pg.mkPen(color='red', width=1)
        pen2 = pg.mkPen(color='green', width=1)
        pen3 = pg.mkPen(color='blue', width=1)
        pen4 = pg.mkPen(color='orange', width=1)

        self.graphWidget.setLabel('left', 'Bath temp [ºC]', color='red', size=30)
        self.graphWidget.setLabel('right', 'Setpoint temp [ºC]', color='green', size=30)
        self.graphWidget.setLabel('bottom', 'Time', size=30)

        self.new_line1 = self.graphWidget.plot(*zip(*self.bath_temp), name="Bath temp.", pen=pen)
        self.line2 = self.graphWidget.plot(*zip(*self.setpoint), name="Setpoint temp.", pen=pen2)
        self.line3 = self.graphWidget.plot(*zip(*self.adam0), name="ADAM_0", pen=pen3)
        self.line4 = self.graphWidget.plot(*zip(*self.adam1), name="ADAM_1", pen=pen4)

        self.show()

    def video_settings(self):
        self.VideoSettingsUi = VideoSettingsUi(self.video_thread)
        self.VideoSettingsUi.show()

    def save_pic(self):
        ret, cv_img = self.video_thread.cap.read()

        if len(self.exp_list) == 1:
            experiment = self.exp_list[0]
            fo = experiment.experiment_path / 'pics' / time.strftime("%Y%m%d%H%M%S.jpg", time.localtime())
            cv_img = cv2.rotate(cv_img, cv2.ROTATE_90_CLOCKWISE)
            cv2.imwrite(str(fo), cv_img)
        elif len(self.exp_list) >= 2:
            # cv_img = cv2.rotate(cv_img, cv2.ROTATE_90_CLOCKWISE)
            # cv_img = convert_qt_cv(self.image_frame.pixmap().toImage())

            croped = cv_img  # auto_crop(cv_img)

            height, width = croped.shape[:2]
            split_width = width // len(self.exp_list)

            for i, experiment in enumerate(self.exp_list):
                fo = experiment.experiment_path / 'pics' / time.strftime(f"%Y%m%d%H%M%S.jpg", time.localtime())
                segment = croped[:, i * split_width : (i+1) * split_width]
                cv2.imwrite(str(fo), segment)


    def setup_saving(self):
        log_fmt = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        logger = logging.getLogger('')

        windows_title = ''

        if not self.saveCheckBox.isChecked():
            self.timer2.stop()
            logging.info("Stopped saving data!")
            return

        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)

        logging.basicConfig(level=logging.INFO,
                            format=log_fmt,
                            filemode='w')

        for experiment in self.exp_list:
            file_handler = logging.FileHandler(experiment.experiment_path / f'{experiment.metadata.label}.log')
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(logging.Formatter(log_fmt))
            logger.addHandler(file_handler)

            with open(experiment.experiment_path / "sensors_data.csv", "a") as fo:
                fo.write(f'datetime, 'f'SP,' f'BT,' f'RTD0,' f'RTD1,' f'TEMP,' f'RH\n')

            logging.info(f'Sensors data file created: {experiment.experiment_path / "sensors_data.csv"}')

            windows_title += experiment.metadata.label
            windows_title += ' - '

        self.setWindowTitle(windows_title)

        logging.info(f"Software version: {__version__}")

        # logging.info(f"Experiment directory created: {self.experiment.experiment_path}")

        self.timer2 = QTimer()
        self.timer2.setInterval(self.pictureIntervalSpinBox.value() * 1000)
        self.timer2.timeout.connect(self.save_pic)
        self.timer2.start()

    def connect_video(self):
        logging.info("Connecting Camera")

        # Setup video widget
        self.image_frame = self.findChild(QtWidgets.QLabel, 'videoLabel')
        self.video_thread = VideoThread(self.cameraID.value())
        # connect its signal to the update_image slot
        self.video_thread.change_pixmap_signal.connect(self.update_image)
        # start the thread
        self.video_thread.start()

        logging.info("Camera connected")

    def connect_chiller(self):
        # Setup thread for temperature I/O
        self.data_worker = DataWorker(float(self.temp_set.text()))
        self.data_worker.read_data_signal.connect(self.read_sensors_data)
        self.data_worker.start()

    def start_scan(self):
        max_temp = float(self.maxTemp.text())
        min_temp = float(self.minTemp.text())
        cooling_rate = float(self.coolingRate.text())
        heating_rate = float(self.heatingRate.text())

        self.temp_worker = TempThread(max_temp, min_temp, cooling_rate, heating_rate)
        self.temp_worker.temp_signal.connect(self.set_temp2)
        self.temp_worker.start()

    @pyqtSlot(object)
    def set_temp2(self, t):
        logging.info(f'Setting temperature to: {t}')
        try:
            self.data_worker.daq.set_temperature(t)
        except AttributeError:
            pass

    @pyqtSlot(object)
    def read_sensors_data(self, data):
        t = time.time()

        BT = data['BT']
        SP = data['SP']
        RTD0, RTD1 = data['RTD0'], data['RTD1']
        TEMP, RH = data['TEMP'], data['RH']

        self.bath_temp.append((t, BT))
        self.setpoint.append((t, SP))
        self.adam0.append((t, RTD0))
        self.adam1.append((t, RTD1))
        self.TEMP.append((t, TEMP))
        self.RH.append((t, RH))

        if self.saveCheckBox.isChecked():
            for experiment in self.exp_list:
                with open(experiment.experiment_path / "sensors_data.csv", "a") as fo:
                    fo.write(f'{time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t))},'
                             f'{SP:.2f},' f'{BT:.2f},' f'{RTD0:.2f},' f'{RTD1:.2f},' f'{TEMP:.2f},' f'{RH:.2f}\n')

        self.update_temp_plot()

    def clear_data(self):
        self.bath_temp = []
        self.setpoint = []
        self.adam0 = []
        self.adam1 = []

    def exit(self):

        try:
            self.data_worker.daq.daq_device.release()
        except AttributeError:
            logging.warning("DAQ device not initialized")

        try:
            self.video_thread.stop()
        except AttributeError:
            logging.warning("Camera not initialized")

        logging.info("Exiting experiment")

        sys.exit()

    def update_temp_plot(self):
        self.new_line1.setData(*zip(*self.bath_temp))
        self.line2.setData(*zip(*self.setpoint))
        self.line3.setData(*zip(*self.adam0))
        self.line4.setData(*zip(*self.adam1))

        self.lcdBT.display(f"{self.bath_temp[-1][1]:.02f}")
        self.lcdSP.display(f"{self.setpoint[-1][1]:.02f}")
        self.lcdRTD1.display(f"{self.adam0[-1][1]:.02f}")
        self.lcdRTD2.display(f"{self.adam1[-1][1]:.02f}")
        self.lcdTEMP.display(str(f"{self.TEMP[-1][1]:.02f}"))
        self.lcdRH.display(str(f"{self.RH[-1][1]:.02f}"))

    def set_temp(self):
        t = float(self.temp_set.text())
        logging.info(f'Setting temperature to: {t}')
        self.data_worker.chiller.set_temperature(t)

    @pyqtSlot(np.ndarray)
    def update_image(self, cv_img):
        """Updates the image_label with a new opencv image"""
        qt_img = convert_cv_qt(cv_img)
        self.image_frame.setPixmap(qt_img)


class QPlainTextEditLogger(logging.Handler):
    def __init__(self, parent):
        super(QPlainTextEditLogger, self).__init__()

        self.widget = QPlainTextEdit(parent)
        self.widget.setReadOnly(True)

    def emit(self, record):
        msg = self.format(record)
        self.widget.appendPlainText(msg)

    def write(self, m):
        pass


class TimeAxisItem(pg.AxisItem):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setLabel(text='Time', units=None)
        self.enableAutoSIPrefix(False)

    def tickStrings(self, values, scale, spacing):
        return [time.strftime("%H:%M:%S", time.localtime(value)) for value in values]


def main():
    app = QtWidgets.QApplication(sys.argv)
    window = ExperimentUi()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    log_fmt = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logging.basicConfig(level=logging.INFO, format=log_fmt)
    main()
