import sys
import time
import cv2
import logging

import numpy as np
import pyqtgraph as pg

from PyQt5 import QtGui
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import QTimer, pyqtSlot, Qt
from PyQt5.QtWidgets import *

from src import paths

from src.daq import mccdaq
from src.gui.video import VideoThread
from src.daq.ADAMlib import ADAMConnection, ADAM4015
from src.daq.IniLoader import IniLoader


class TimeAxisItem(pg.AxisItem):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setLabel(text='Time', units=None)
        self.enableAutoSIPrefix(False)

    def tickStrings(self, values, scale, spacing):
        return [time.strftime("%H:%M:%S", time.localtime(value)) for value in values]


class Window(QWidget):
    def __init__(self):
        super().__init__()

        self.adam = None
        self.setWindowTitle("Lauda temperature control")
        self.setGeometry(50, 50, 1200, 660)

        self.display_width = 640
        self.display_height = 480

        self.timer = None
        self.daq = None
        self.camera = None

        self.line1 = None
        self.line2 = None
        self.line3 = None
        self.line4 = None

        self.bath_temp = []
        self.setpoint = []
        self.adam0 = []
        self.adam1 = []

        self.UI()

    def UI(self):
        self.setStyleSheet("background-color:white;font-size:12pt;font-family:Times;")

        temperatureLayout = QVBoxLayout()
        mainLayout = QHBoxLayout()

        bottomFormLayout = QFormLayout()
        topLayout = QVBoxLayout()

        videoLayout = QVBoxLayout()

        temperatureLayout.addLayout(topLayout)
        temperatureLayout.addLayout(bottomFormLayout)

        mainLayout.addLayout(temperatureLayout)
        mainLayout.addLayout(videoLayout)

        self.image_label = QLabel(self)
        # self.image_label.resize(self.display_width, self.display_height)
        videoLayout.addWidget(self.image_label)
        # create the video capture thread
        self.thread = VideoThread()
        # connect its signal to the update_image slot
        self.thread.change_pixmap_signal.connect(self.update_image)
        # start the thread
        self.thread.start()

        self.graphWidget = pg.PlotWidget(axisItems={'bottom': TimeAxisItem(orientation='bottom')})
        self.graphWidget.showGrid(x=True, y=True, alpha=0.2)

        self.temp_set_label = QLabel("Set temperature :")
        self.temp_set = QLineEdit('17')
        self.temp_set_btn = QPushButton("Set", self)
        self.temp_set_btn.clicked.connect(self.set_temp)
        setTempWidget = QHBoxLayout()
        setTempWidget.addWidget(self.temp_set)
        setTempWidget.addWidget(self.temp_set_btn)

        self.accx = QLabel("Setpoint [CH4] :")
        self.setpoint_value = QLabel("...")
        self.accx.setStyleSheet("color:green;")
        self.setpoint_value.setStyleSheet("color:green;")

        self.accy = QLabel("Bath temp [CH5] :")
        self.bath_temp_value = QLabel("...")
        self.accy.setStyleSheet("color:red;")
        self.bath_temp_value.setStyleSheet("color:red;")

        self.btn_connect = QPushButton("Connect", self)
        self.btn_connect.clicked.connect(self.connect_system)

        self.btn_exit = QPushButton("Exit", self)
        self.btn_exit.clicked.connect(self.exit)

        self.btn_clear_plot = QPushButton("Clear plot", self)
        self.btn_clear_plot.clicked.connect(self.clear_plot)

        bottomFormLayout.setContentsMargins(10, 10, 10, 10)
        bottomFormLayout.addRow(self.temp_set_label, setTempWidget)
        bottomFormLayout.addRow(self.btn_connect)
        bottomFormLayout.addRow(self.btn_clear_plot)
        bottomFormLayout.addRow(self.btn_exit)
        bottomFormLayout.addRow(self.accx, self.setpoint_value)
        bottomFormLayout.addRow(self.accy, self.bath_temp_value)

        topLayout.addWidget(self.graphWidget)

        self.setLayout(mainLayout)

        self.timer = QTimer()
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.update_temp_plot)
        
        self.show()

    def set_temp(self):
        t = float(self.temp_set.text())
        logging.info(f'Setting temperature to: {t}')
        self.daq.set_temperature(t)

    def connect_system(self):
        logging.info("Connecting System")

        # Connect to ADAM-4015
        ini = IniLoader.load('perezfo', '../../notebooks/test.ini')
        conn = ADAMConnection(ini['SERIAL'])
        self.adam = ADAM4015(conn, 0x24)

        # Connect MC-DAQ (USB-1808) and set the initial temperature
        self.daq = mccdaq.Daq()
        self.daq.set_starting_temp(float(self.temp_set.text()))

        # Start the timer
        self.timer.start()

    def exit(self):
        self.timer.stop()
        try:
            self.daq.daq_device.release()
        except AttributeError:
            logging.error("DAQ device not initialized")

        self.thread.stop()
        sys.exit()

    def read_sensors_data(self):
        t = time.time()

        self.bath_temp.append((t, self.daq.get_bath_temp(samples=20, interval=1e-3)))
        self.setpoint.append((t, self.daq.get_setpoint_temp(samples=20, interval=1e-3)))
        self.adam0.append((t, self.adam.GetTemp(ch=0)))
        self.adam1.append((t, self.adam.GetTemp(ch=1)))

        self.thread.setpoint_temp_text = f'{(self.setpoint[-1][1]):.2f}'
        self.thread.bath_temp_text = f'{(self.bath_temp[-1][1]):.2f}'
        self.thread.ADAMCH0_temp_text = f'{(self.adam0[-1][1]):.2f}'
        self.thread.ADAMCH1_temp_text = f'{(self.adam1[-1][1]):.2f}'

        self.setpoint_value.setText(f'{(self.setpoint[-1][1] / 100 * 1e3):.3f} mV')
        self.bath_temp_value.setText(f'{(self.bath_temp[-1][1] / 100 * 1e3):.3f} mV')

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

    def clear_plot(self):
        self.bath_temp = []
        self.setpoint = []
        self.adam0 = []
        self.adam1 = []

        self.graphWidget.clear()

    @pyqtSlot(np.ndarray)
    def update_image(self, cv_img):
        """Updates the image_label with a new opencv image"""
        qt_img = self.convert_cv_qt(cv_img)
        self.image_label.setPixmap(qt_img)

    def convert_cv_qt(self, cv_img):
        """Convert from an opencv image to QPixmap"""
        rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        convert_to_Qt_format = QtGui.QImage(rgb_image.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)
        p = convert_to_Qt_format.scaled(self.display_width, self.display_height, Qt.KeepAspectRatio)

        return QPixmap.fromImage(p)


def main():
    App = QApplication(sys.argv)
    window = Window()
    sys.exit(App.exec_())


if __name__ == '__main__':
    filename = paths.project_dir / 'myfirstlog.log'
    log_fmt = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logging.basicConfig(filename=filename, level=logging.INFO, format=log_fmt)
    main()
