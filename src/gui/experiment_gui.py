#!/usr/bin/env python3
"""The scan window: camera, chiller, temperature ramp and data logging."""

import logging
import time

import cv2
import numpy as np
import pyqtgraph as pg

from PyQt6 import QtGui, QtWidgets, uic
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QPixmap

from src import __version__, paths
from src.gui.threads import DataWorker, TempThread, VideoThread
from src.gui.video import VideoSettingsUi

VIDEO_DISPLAY_WIDTH = 525
VIDEO_DISPLAY_HEIGHT = 359

#: Columns of sensors_data.csv, in order. The header used to list four columns
#: while five values were written on every row.
SENSOR_COLUMNS = ('datetime', 'SP', 'BT', 'RTD0', 'RTD1')

LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'


def convert_cv_qt(cv_img):
    """Convert from an opencv image to QPixmap"""
    rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb_image.shape
    bytes_per_line = ch * w
    convert_to_Qt_format = QtGui.QImage(rgb_image.data, w, h, bytes_per_line, QtGui.QImage.Format.Format_RGB888)
    p = convert_to_Qt_format.scaled(VIDEO_DISPLAY_WIDTH, VIDEO_DISPLAY_HEIGHT, Qt.AspectRatioMode.KeepAspectRatio)

    return QPixmap.fromImage(p)


class ExperimentUi(QtWidgets.QMainWindow):
    """Drives one scan over one or two PCR plates."""

    def __init__(self, exp_list, *args, **kwargs):
        super(ExperimentUi, self).__init__(*args, **kwargs)

        uic.loadUi(paths.src_module_dir / 'gui' / 'experiment.ui', self)

        self.exp_list = exp_list
        self.bath_temp = []
        self.setpoint = []
        self.adam0 = []
        self.adam1 = []

        self.video_thread = None
        self.data_worker = None
        self.temp_worker = None
        self.image_frame = self.findChild(QtWidgets.QLabel, 'videoLabel')
        self.picture_timer = None
        self.VideoSettingsUi = None
        self._file_logging_ready = False

        # Connect buttons
        self.button_set_temp = self.findChild(QtWidgets.QPushButton, 'setTempButton')
        self.button_set_temp.clicked.connect(self.set_temp_from_form)

        self.btn_connect_video = self.findChild(QtWidgets.QPushButton, 'connectVideoButton')
        self.btn_connect_video.clicked.connect(self.connect_video)

        self.btn_connect_lauda = self.findChild(QtWidgets.QPushButton, 'connectLAUDAButton')
        self.btn_connect_lauda.clicked.connect(self.connect_chiller)

        self.btn_start_scan = self.findChild(QtWidgets.QPushButton, 'startScanButton')
        self.btn_start_scan.clicked.connect(self.start_scan)

        self.btn_stop_scan = self.findChild(QtWidgets.QPushButton, 'stopScanButton')
        self.btn_stop_scan.clicked.connect(self.stop_scan)

        self.btn_exit = self.findChild(QtWidgets.QPushButton, 'exitButton')
        self.btn_exit.clicked.connect(self.exit)

        self.btn_endscan = self.findChild(QtWidgets.QPushButton, 'EndScanpushButton')
        self.btn_endscan.clicked.connect(self.end_scan)

        self.btn_clear_plot = self.findChild(QtWidgets.QPushButton, 'clearPlotButton')
        self.btn_clear_plot.clicked.connect(self.clear_data)

        self.btn_video_settings = self.findChild(QtWidgets.QPushButton, 'videoSettingsButton')
        self.btn_video_settings.clicked.connect(self.video_settings)

        # Show time as HH:MM:SS on the x axis
        self.graphWidget.setAxisItems(axisItems={'bottom': TimeAxisItem(orientation='bottom')})

        self.saveCheckBox.stateChanged.connect(self.setup_saving)

        self._setup_log_widget()

        self.graphWidget.setLabel('left', 'Temperature [ºC]', color='red', size=30)
        self.graphWidget.setLabel('bottom', 'Time', size=30)
        self.graphWidget.addLegend()

        self.line_bath_temp = self.graphWidget.plot([], [], name="Bath temp.", pen=pg.mkPen(color='red', width=1))
        self.line_setpoint = self.graphWidget.plot([], [], name="Setpoint temp.", pen=pg.mkPen(color='green', width=1))
        self.line_adam0 = self.graphWidget.plot([], [], name="ADAM_0", pen=pg.mkPen(color='blue', width=1))

        self.setWindowTitle(' - '.join(e.metadata.label for e in self.exp_list if e.metadata))

        self.show()

    # -- logging -------------------------------------------------------------

    def _setup_log_widget(self):
        """Mirror the log into the window, if the .ui provides a place for it.

        ``experiment.ui`` currently has no ``logTextEdit`` widget; add a
        QPlainTextEdit with that name to get the log panel back.
        """
        self.log_text_edit = self.findChild(QtWidgets.QPlainTextEdit, 'logTextEdit')
        self.log_handler = None

        if self.log_text_edit is None:
            logging.debug("No 'logTextEdit' widget in experiment.ui, skipping the log panel")
            return

        self.log_handler = QPlainTextEditLogger(self.log_text_edit)
        self.log_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logging.getLogger().addHandler(self.log_handler)

    def _setup_file_logging(self):
        """Also write the log to a file inside each experiment directory."""
        if self._file_logging_ready:
            return

        logger = logging.getLogger()
        for experiment in self.exp_list:
            log_file = experiment.experiment_path / f'{experiment.metadata.label}.log'
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
            logger.addHandler(file_handler)
            logging.info(f"Logging to: {log_file}")

        self._file_logging_ready = True

    # -- sensors file --------------------------------------------------------

    @staticmethod
    def _ensure_sensors_file(experiment):
        """Create sensors_data.csv with its header, once per experiment."""
        path = experiment.sensors_file
        if path.exists() and path.stat().st_size > 0:
            return path

        with open(path, 'w') as fo:
            fo.write(','.join(SENSOR_COLUMNS) + '\n')
        logging.info(f"Sensors data file created: {path}")
        return path

    def _append_sensors_row(self, timestamp, sp, bt, rtd0, rtd1):
        row = (f'{time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))},'
               f'{sp:.2f},{bt:.2f},{rtd0:.2f},{rtd1:.2f}\n')

        for experiment in self.exp_list:
            try:
                with open(experiment.sensors_file, 'a') as fo:
                    fo.write(row)
            except Exception as e:
                logging.error(f"Error saving data for experiment {experiment.exp_name}: {e}")

    # -- scanning ------------------------------------------------------------

    def start_scan(self):
        if self.temp_worker is not None and self.temp_worker.isRunning():
            logging.warning("A scan is already running")
            return

        if self.data_worker is None or not self.data_worker.connected:
            self._warn("Connect the chiller before starting a scan.")
            return

        try:
            self.temp_worker = TempThread(max_temp=float(self.maxTemp.text()),
                                          min_temp=float(self.minTemp.text()),
                                          cooling_rate=float(self.coolingRate.text()),
                                          heating_rate=float(self.heatingRate.text()))
        except ValueError as e:
            self._warn(f"Cannot start the scan: {e}")
            return

        self.temp_worker.temp_signal.connect(self.set_temp)
        self.temp_worker.start()

        self.saveCheckBox.setChecked(True)
        logging.info("Scan started")

    def _stop_ramp(self):
        if self.temp_worker is None or not self.temp_worker.isRunning():
            logging.info("No scan is running")
            return False

        self.temp_worker.stop()
        return True

    def stop_scan(self):
        if self._stop_ramp():
            logging.info("Scan terminated!")

    def end_scan(self):
        self.saveCheckBox.setChecked(False)
        self._stop_ramp()
        self.set_temp(0)
        logging.info("Scan terminated!")

    def set_temp_from_form(self):
        try:
            self.set_temp(float(self.targetTemp.text()))
        except ValueError:
            self._warn(f"{self.targetTemp.text()!r} is not a valid temperature.")

    @pyqtSlot(object)
    def set_temp(self, t):
        logging.info(f'Setting temperature to: {t}')
        if self.data_worker is None:
            logging.error("Error setting temperature: chiller not connected")
            return
        self.data_worker.set_temperature(t)

    # -- pictures ------------------------------------------------------------

    def video_settings(self):
        if self.video_thread is None:
            self._warn("Connect the camera first.")
            return
        self.VideoSettingsUi = VideoSettingsUi(self.video_thread)
        self.VideoSettingsUi.show()

    def save_pic(self):
        """Save the current frame, one picture per experiment.

        The frame comes from the video thread's last capture: calling
        ``cap.read()`` here would race with the thread that is already reading
        the same camera.
        """
        if self.video_thread is None or self.video_thread.last_frame is None:
            logging.warning("No frame available to save")
            return

        # Saved unrotated, side by side as the camera sees them: the analysis
        # applies metadata.rotation itself (see FrESHExperiment.process_images),
        # so rotating here would turn the plates twice.
        cv_img = self.video_thread.last_frame
        file_name = time.strftime("%Y%m%d%H%M%S.jpg", time.localtime())

        width = cv_img.shape[1]
        split_width = width // len(self.exp_list)

        for i, experiment in enumerate(self.exp_list):
            segment = cv_img if len(self.exp_list) == 1 else cv_img[:, i * split_width:(i + 1) * split_width]
            cv2.imwrite(str(experiment.pics_path / file_name), segment)

    def setup_saving(self):
        """Start or stop writing pictures and sensor readings to disk."""
        if not self.saveCheckBox.isChecked():
            if self.picture_timer is not None:
                self.picture_timer.stop()
            logging.info("Stopped saving data!")
            return

        self._setup_file_logging()

        for experiment in self.exp_list:
            self._ensure_sensors_file(experiment)

        logging.info(f"Software version: {__version__}")

        if self.picture_timer is None:
            self.picture_timer = QTimer()
            self.picture_timer.timeout.connect(self.save_pic)

        self.picture_timer.setInterval(self.pictureIntervalSpinBox.value() * 1000)
        self.picture_timer.start()
        logging.info(f"Saving a picture every {self.pictureIntervalSpinBox.value()} s")

    # -- connections ---------------------------------------------------------

    def connect_video(self):
        logging.info("Connecting Camera")

        if self.video_thread is not None:
            self.video_thread.change_pixmap_signal.disconnect(self.update_image)
            self.video_thread.stop()

        self.video_thread = VideoThread(self.cameraID.value())
        self.video_thread.change_pixmap_signal.connect(self.update_image)
        self.video_thread.start()

        logging.info("Camera connected")

    def connect_chiller(self):
        if self.data_worker is not None and self.data_worker.isRunning():
            logging.warning("The chiller is already connected")
            return

        try:
            initial_temp = float(self.targetTemp.text())
        except ValueError:
            initial_temp = 0.0

        self.data_worker = DataWorker(initial_temp)
        self.data_worker.read_data_signal.connect(self.read_sensors_data)
        self.data_worker.start()

    @pyqtSlot(object)
    def read_sensors_data(self, data):
        try:
            if data is None:
                logging.warning("Received null data from sensors")
                return

            t = time.time()

            BT = data.get('BT', 0.0)
            SP = data.get('SP', 0.0)
            RTD0 = data.get('RTD0', 0.0)
            RTD1 = data.get('RTD1', 0.0)

            self.bath_temp.append((t, BT))
            self.setpoint.append((t, SP))
            self.adam0.append((t, RTD0))
            self.adam1.append((t, RTD1))

            if self.saveCheckBox.isChecked():
                self._append_sensors_row(t, SP, BT, RTD0, RTD1)

            self.update_temp_plot()

        except Exception as e:
            logging.error(f"Error processing sensor data: {e}")

    # -- plotting ------------------------------------------------------------

    def clear_data(self):
        self.bath_temp = []
        self.setpoint = []
        self.adam0 = []
        self.adam1 = []

        for line in (self.line_bath_temp, self.line_setpoint, self.line_adam0):
            line.setData([], [])

    def update_temp_plot(self):
        if not self.bath_temp:
            return

        self.line_bath_temp.setData(*zip(*self.bath_temp))
        self.line_setpoint.setData(*zip(*self.setpoint))
        self.line_adam0.setData(*zip(*self.adam0))

        self.lcdBT.display(f"{self.bath_temp[-1][1]:.02f}")
        self.lcdSP.display(f"{self.setpoint[-1][1]:.02f}")
        self.lcdRTD1.display(f"{self.adam0[-1][1]:.02f}")

    @pyqtSlot(np.ndarray)
    def update_image(self, cv_img):
        """Updates the image_label with a new opencv image"""
        if self.image_frame is not None:
            self.image_frame.setPixmap(convert_cv_qt(cv_img))

    # -- shutting down -------------------------------------------------------

    def _warn(self, message):
        logging.warning(message)
        QtWidgets.QMessageBox.warning(self, "FrESH", message)

    def shutdown(self):
        """Stop every worker and release the hardware."""
        if self.picture_timer is not None:
            self.picture_timer.stop()

        if self.temp_worker is not None and self.temp_worker.isRunning():
            self.temp_worker.stop()

        if self.video_thread is not None:
            self.video_thread.stop()
            self.video_thread = None

        if self.data_worker is not None:
            # Closes the serial port / releases the DAQ board too.
            self.data_worker.stop()
            self.data_worker = None

        if self.log_handler is not None:
            logging.getLogger().removeHandler(self.log_handler)
            self.log_handler = None

    def closeEvent(self, event):
        """Also clean up when the window is closed with the title bar."""
        self.shutdown()
        super().closeEvent(event)

    def exit(self):
        logging.info("Exiting experiment")
        self.shutdown()
        self.close()
        QtWidgets.QApplication.quit()


class QPlainTextEditLogger(logging.Handler):
    """A logging handler that appends to a QPlainTextEdit.

    Records arrive from the worker threads, and Qt widgets may only be touched
    from the GUI thread, so the text is handed over through a signal.
    """

    class _Bridge(QtWidgets.QWidget):
        message = pyqtSignal(str)

    def __init__(self, widget):
        super(QPlainTextEditLogger, self).__init__()

        self.widget = widget
        self.widget.setReadOnly(True)

        self._bridge = self._Bridge()
        self._bridge.message.connect(self.widget.appendPlainText)

    def emit(self, record):
        try:
            self._bridge.message.emit(self.format(record))
        except RuntimeError:
            # The widget is gone (window closed); nothing to do.
            pass


class TimeAxisItem(pg.AxisItem):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setLabel(text='Time', units=None)
        self.enableAutoSIPrefix(False)

    def tickStrings(self, values, scale, spacing):
        return [time.strftime("%H:%M:%S", time.localtime(value)) for value in values]
