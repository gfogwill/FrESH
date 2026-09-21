#!/usr/bin/env python3
"""The scan window: camera, chiller, temperature ramp and data logging.

Two ways to run the chiller from here:

* **Start ramp** -- the old manual behaviour. The setpoint cycles between the
  scan start temperature and the minimum until it is stopped, everything is
  recorded into one folder.
* **Start series** -- an automated freeze/thaw series. Each cycle cools down
  (recording), holds until the sample is frozen, thaws, and comes back; every
  cycle gets its own folder so it can be analysed on its own. See
  :mod:`src.experiment.series`.
"""

import copy
import json
import logging
import time

import cv2
import numpy as np
import pyqtgraph as pg

from PyQt6 import QtGui, QtWidgets, uic
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QPixmap

from src import __version__, paths
from src.experiment.experiment import FrESHExperiment
from src.experiment.series import SeriesController, SeriesSettings
from src.gui.threads import DataWorker, VideoThread
from src.gui.video import VideoSettingsUi

VIDEO_DISPLAY_WIDTH = 525
VIDEO_DISPLAY_HEIGHT = 359

#: Columns of sensors_data.csv, in order.
SENSOR_COLUMNS = ('datetime', 'SP', 'BT', 'RTD0', 'RTD1')

LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

#: Sensor the freeze hold watches, by the text of holdSourceComboBox.
HOLD_SOURCES = {'Bath (BT)': 'BT', 'Probe (RTD0)': 'RTD0'}


def convert_cv_qt(cv_img):
    """Convert from an opencv image to QPixmap"""
    rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb_image.shape
    bytes_per_line = ch * w
    convert_to_Qt_format = QtGui.QImage(rgb_image.data, w, h, bytes_per_line, QtGui.QImage.Format.Format_RGB888)
    p = convert_to_Qt_format.scaled(VIDEO_DISPLAY_WIDTH, VIDEO_DISPLAY_HEIGHT, Qt.AspectRatioMode.KeepAspectRatio)

    return QPixmap.fromImage(p)


def format_duration(seconds):
    """'2 h 45 min', for the series estimate."""
    if seconds is None:
        return "unbounded"

    hours, minutes = divmod(int(round(seconds / 60)), 60)
    return f"{hours} h {minutes:02d} min" if hours else f"{minutes} min"


class ExperimentUi(QtWidgets.QMainWindow):
    """Drives scans over one or two PCR plates."""

    def __init__(self, metadata_list, *args, **kwargs):
        super(ExperimentUi, self).__init__(*args, **kwargs)

        uic.loadUi(paths.src_module_dir / 'gui' / 'experiment.ui', self)

        #: The metadata the operator confirmed, used as a template: every cycle
        #: gets its own copy, with its own cycle number and folder.
        self.metadata_list = list(metadata_list)
        self.series_id = time.strftime('%Y%m%d%H%M', time.localtime())

        #: Experiments of the cycle currently open. Created on demand, so that
        #: closing the window without scanning leaves no empty folders behind.
        self.exp_list = []
        self.current_cycle = None
        self.cycle_log_handlers = []

        self.series = None
        self.series_dir = None
        self.series_sensors_file = None

        self.bath_temp = []
        self.setpoint = []
        self.adam0 = []
        self.adam1 = []

        self.video_thread = None
        self.data_worker = None
        self.image_frame = self.findChild(QtWidgets.QLabel, 'videoLabel')
        self.picture_timer = None
        self.VideoSettingsUi = None

        self._connect_buttons()

        # Show time as HH:MM:SS on the x axis
        self.graphWidget.setAxisItems(axisItems={'bottom': TimeAxisItem(orientation='bottom')})

        self._setup_log_widget()

        self.graphWidget.setLabel('left', 'Temperature [ºC]', color='red', size=30)
        self.graphWidget.setLabel('bottom', 'Time', size=30)
        self.graphWidget.addLegend()

        self.line_bath_temp = self.graphWidget.plot([], [], name="Bath temp.", pen=pg.mkPen(color='red', width=1))
        self.line_setpoint = self.graphWidget.plot([], [], name="Setpoint temp.", pen=pg.mkPen(color='green', width=1))
        self.line_adam0 = self.graphWidget.plot([], [], name="RTD0", pen=pg.mkPen(color='blue', width=1))

        self.setWindowTitle(' - '.join(m.label for m in self.metadata_list))
        self._update_series_estimate()

        self.show()

    def _connect_buttons(self):
        self.setTempButton.clicked.connect(self.set_temp_from_form)
        self.connectVideoButton.clicked.connect(self.connect_video)
        self.connectLAUDAButton.clicked.connect(self.connect_chiller)
        self.startScanButton.clicked.connect(self.start_scan)
        self.stopScanButton.clicked.connect(self.stop_scan)
        self.exitButton.clicked.connect(self.exit)
        self.EndScanpushButton.clicked.connect(self.end_scan)
        self.clearPlotButton.clicked.connect(self.clear_data)
        self.videoSettingsButton.clicked.connect(self.video_settings)
        self.saveCheckBox.stateChanged.connect(self.setup_saving)

        self.startSeriesButton.clicked.connect(self.start_series)
        self.abortSeriesButton.clicked.connect(self.abort_series)

        for widget in (self.maxTemp, self.minTemp, self.coolingRate, self.heatingRate,
                       self.thawTemp, self.holdColdMinutes, self.holdWarmMinutes):
            widget.textChanged.connect(self._update_series_estimate)
        self.cyclesSpinBox.valueChanged.connect(self._update_series_estimate)

    # -- logging -------------------------------------------------------------

    def _setup_log_widget(self):
        """Mirror the log into the window."""
        self.log_text_edit = self.findChild(QtWidgets.QPlainTextEdit, 'logTextEdit')
        self.log_handler = None

        if self.log_text_edit is None:
            logging.debug("No 'logTextEdit' widget in experiment.ui, skipping the log panel")
            return

        self.log_handler = QPlainTextEditLogger(self.log_text_edit)
        self.log_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logging.getLogger().addHandler(self.log_handler)

    def _attach_log_file(self, path, store):
        handler = logging.FileHandler(path)
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logging.getLogger().addHandler(handler)
        store.append(handler)

    def _detach_cycle_logs(self):
        """A 50-cycle series must not leave 100 file handlers on the logger."""
        for handler in self.cycle_log_handlers:
            logging.getLogger().removeHandler(handler)
            handler.close()
        self.cycle_log_handlers = []

    # -- cycles --------------------------------------------------------------

    def _cycle_folder_name(self, label, cycle):
        if cycle is None:
            return f'{self.series_id}_{label}'
        return f'{self.series_id}_{label}_c{cycle:03d}'

    def _open_cycle(self, cycle=None):
        """Create this cycle's experiment folders and point the recording at them."""
        self._close_cycle()

        self.current_cycle = cycle
        self.exp_list = []

        for template in self.metadata_list:
            metadata = copy.deepcopy(template)
            metadata.series_id = self.series_id
            metadata.cycle_number = cycle

            experiment = FrESHExperiment(self._cycle_folder_name(metadata.label, cycle))
            experiment.set_metadata(metadata)
            self._ensure_sensors_file(experiment)
            self._attach_log_file(experiment.experiment_path / f'{metadata.label}.log',
                                  self.cycle_log_handlers)

            self.exp_list.append(experiment)

        logging.info(f"Software version: {__version__}")
        return self.exp_list

    def _close_cycle(self):
        self._detach_cycle_logs()

    # -- sensors files -------------------------------------------------------

    @staticmethod
    def _write_sensors_header(path):
        if path.exists() and path.stat().st_size > 0:
            return path
        with open(path, 'w') as fo:
            fo.write(','.join(SENSOR_COLUMNS) + '\n')
        return path

    def _ensure_sensors_file(self, experiment):
        """Create sensors_data.csv with its header, once per experiment."""
        path = self._write_sensors_header(experiment.sensors_file)
        logging.info(f"Sensors data file: {path}")
        return path

    @staticmethod
    def _sensors_row(timestamp, sp, bt, rtd0, rtd1):
        return (f'{time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))},'
                f'{sp:.2f},{bt:.2f},{rtd0:.2f},{rtd1:.2f}\n')

    def _append_sensors_row(self, row):
        for experiment in self.exp_list:
            try:
                with open(experiment.sensors_file, 'a') as fo:
                    fo.write(row)
            except Exception as e:
                logging.error(f"Error saving data for experiment {experiment.exp_name}: {e}")

    # -- the manual ramp -----------------------------------------------------

    def _float_field(self, widget, name):
        try:
            return float(widget.text())
        except ValueError:
            raise ValueError(f"{name} is not a valid number: {widget.text()!r}")

    def _ramp_settings(self):
        """Settings for the manual ramp: no holds, no per-cycle folders."""
        return SeriesSettings(
            scan_start_temp=self._float_field(self.maxTemp, 'Scan start temp'),
            min_temp=self._float_field(self.minTemp, 'Min. setpoint'),
            freeze_temp=self._float_field(self.minTemp, 'Min. setpoint'),
            thaw_temp=self._float_field(self.maxTemp, 'Scan start temp'),
            cooling_rate=self._float_field(self.coolingRate, 'Cooling rate'),
            heating_rate=self._float_field(self.heatingRate, 'Heating rate'),
            hold_cold_minutes=0.0, hold_warm_minutes=0.0,
            cycles=None, folder_per_cycle=False, wait_for_bath=False)

    def start_scan(self):
        if not self._ready_to_run():
            return

        try:
            settings = self._ramp_settings()
            # The manual ramp turns around at the top, so the thaw temperature
            # has to sit above the floor by more than a rounding error.
            settings.thaw_temp = max(settings.thaw_temp, settings.min_temp + 1)
            self._start_controller(settings)
        except ValueError as e:
            self._warn(f"Cannot start the ramp: {e}")
            return

        self.saveCheckBox.setChecked(True)
        logging.info("Ramp started")

    def stop_scan(self):
        if self.series is None:
            logging.info("No ramp is running")
            return
        self.series.stop()

    def end_scan(self):
        if self.series is not None:
            self.series.stop()
        self.saveCheckBox.setChecked(False)
        self.set_temp(0)
        logging.info("Scan terminated!")

    # -- the freeze/thaw series ----------------------------------------------

    def _series_settings(self):
        settings = self._ramp_settings()
        settings.freeze_temp = self._float_field(self.freezeTemp, 'Hold until')
        settings.thaw_temp = self._float_field(self.thawTemp, 'Thaw temp')
        settings.hold_cold_minutes = self._float_field(self.holdColdMinutes, 'Hold time')
        settings.hold_warm_minutes = self._float_field(self.holdWarmMinutes, 'Melt hold time')
        settings.hold_timeout_minutes = self._float_field(self.holdTimeoutMinutes, 'Hold timeout')
        settings.cycles = self.cyclesSpinBox.value()
        settings.folder_per_cycle = True
        settings.wait_for_bath = True
        return settings

    def _update_series_estimate(self):
        """Keep the 'this will take N hours' line in step with the form."""
        try:
            settings = self._series_settings()
            settings.validate()
        except ValueError as e:
            self.seriesEstimateLabel.setText(f"⚠ {e}")
            return

        per_cycle = settings.estimated_cycle_seconds()
        total = settings.estimated_total_seconds()
        text = (f"≈ {format_duration(per_cycle)} per cycle, "
                f"{format_duration(total)} in total (bath lag not included)")

        if self.series is not None:
            text += "  ·  applies from the next cycle"

        self.seriesEstimateLabel.setText(text)

    def start_series(self):
        if self.series is not None:
            self._warn("A series is already running.")
            return

        if not self._ready_to_run():
            return

        try:
            settings = self._series_settings()
            settings.validate()
        except ValueError as e:
            self._warn(f"Cannot start the series: {e}")
            return

        self.series_id = time.strftime('%Y%m%d%H%M', time.localtime())
        self._open_series_dir(settings)
        self._start_controller(settings, follow_form=True)

        self.startSeriesButton.setEnabled(False)
        self.startScanButton.setEnabled(False)
        self.abortSeriesButton.setEnabled(True)

        logging.info(f"Series {self.series_id} started: {settings.cycles} cycles, "
                     f"about {format_duration(settings.estimated_total_seconds())}")

    def abort_series(self):
        if self.series is None:
            return
        self.series.stop('aborted by the operator')

    def _open_series_dir(self, settings):
        """Series-level artifacts, kept out of data/raw so the analysis window
        only ever lists real experiments."""
        self.series_dir = paths.interim_data_path / f'{self.series_id}_series'
        self.series_dir.mkdir(parents=True, exist_ok=True)

        self.series_sensors_file = self._write_sensors_header(
            self.series_dir / 'series_sensors.csv')

        with open(self.series_dir / 'series.json', 'w') as fo:
            json.dump({'series_id': self.series_id,
                       'started': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()),
                       'labels': [m.label for m in self.metadata_list],
                       'software_version': __version__,
                       'hold_source': self.holdSourceComboBox.currentText(),
                       'settings': settings.__dict__}, fo, indent=4, default=str)

        self._attach_log_file(self.series_dir / 'series.log', self.cycle_log_handlers)
        logging.info(f"Series files: {self.series_dir}")

    # -- driving the controller ----------------------------------------------

    def _ready_to_run(self):
        if self.data_worker is None or not self.data_worker.connected:
            self._warn("Connect the chiller first.")
            return False
        return True

    def _start_controller(self, settings, follow_form=False):
        """Run the chiller from ``settings``.

        With ``follow_form`` the controller re-reads the form between cycles,
        so watching the first cycle and then shortening the ramp changes the
        next one. The numbers can be edited at any time; they are picked up in
        the gap between cycles, never in the middle of one.
        """
        provider = self._series_settings if follow_form else None
        self.series = SeriesController(settings, parent=self,
                                       settings_provider=provider)
        self.series.settings_changed.connect(self._on_settings_changed)
        self.series.setpoint_changed.connect(self.set_temp)
        self.series.phase_changed.connect(self._on_phase_changed)
        self.series.cycle_started.connect(self._on_cycle_started)
        self.series.cycle_finished.connect(self._on_cycle_finished)
        self.series.series_finished.connect(self._on_series_ended)
        self.series.aborted.connect(self._on_series_aborted)
        self.series.start()

    @pyqtSlot(int)
    def _on_cycle_started(self, cycle):
        if self.series.settings.folder_per_cycle:
            self._open_cycle(cycle)
            self.saveCheckBox.setChecked(True)
        self._refresh_status()

    @pyqtSlot(int)
    def _on_cycle_finished(self, cycle):
        if self.series is not None and self.series.settings.folder_per_cycle:
            self.saveCheckBox.setChecked(False)
            logging.info(f"Cycle {cycle} recorded into "
                         f"{', '.join(e.exp_name for e in self.exp_list)}")
        self._refresh_status()

    def _on_phase_changed(self, phase, cycle):
        self._refresh_status()

    def _on_settings_changed(self, changes):
        """Tell the operator their edit was taken, and record it in the series."""
        logging.info(f"Series settings updated: {changes}")

        if self.series_dir is None:
            return

        try:
            with open(self.series_dir / 'settings_changes.log', 'a') as fo:
                fo.write(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())} "
                         f"cycle {self.series.cycle + 1}: {changes}\n")
        except Exception as e:
            logging.error(f"Could not record the settings change: {e}")

    def _on_series_ended(self):
        self._finish_series()
        logging.info("Series finished")

    def _on_series_aborted(self, reason):
        self._finish_series()
        self._alert(f"The series was stopped: {reason}.\n\n"
                    f"The setpoint has been set to 0 ºC.")

    def _finish_series(self):
        self.saveCheckBox.setChecked(False)
        self._refresh_status()
        self.series = None
        self.series_sensors_file = None

        # Let go of the last cycle, so switching Save back on later starts a
        # fresh folder instead of appending to cycle N.
        self._close_cycle()
        self.exp_list = []
        self.current_cycle = None

        self.startSeriesButton.setEnabled(True)
        self.startScanButton.setEnabled(True)
        self.abortSeriesButton.setEnabled(False)

    def _refresh_status(self):
        if self.series is None:
            return

        text = self.series.status_text()
        self.seriesStatusLabel.setText(text)

        # Also in the status bar, which stays visible when the parameter column
        # is scrolled: during a three-day series this is the line you look at.
        if self.statusBar() is not None:
            self.statusBar().showMessage(text)

    # -- setting the temperature ---------------------------------------------

    def set_temp_from_form(self):
        try:
            self.set_temp(self._float_field(self.targetTemp, 'Target temp'))
        except ValueError as e:
            self._warn(str(e))

    @pyqtSlot(float)
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

        if not self.exp_list:
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

        if not self.exp_list:
            # Manual scan: open a folder the first time saving is switched on.
            self._open_cycle(None)

        if self.picture_timer is None:
            self.picture_timer = QTimer(self)
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

    def hold_temperature(self, data):
        """The reading the freeze hold watches, per the combo box."""
        key = HOLD_SOURCES.get(self.holdSourceComboBox.currentText(), 'BT')
        return data.get(key)

    @pyqtSlot(object)
    def read_sensors_data(self, data):
        try:
            if data is None:
                logging.warning("Received null data from sensors")
                if self.series is not None:
                    self.series.update_temperature(None)
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

            row = self._sensors_row(t, SP, BT, RTD0, RTD1)

            if self.saveCheckBox.isChecked() and self.exp_list:
                self._append_sensors_row(row)

            # The series file keeps running through the holds and the thaw, so
            # there is a record of whether the chiller ever got where it was told.
            if self.series_sensors_file is not None and self.series is not None:
                try:
                    with open(self.series_sensors_file, 'a') as fo:
                        fo.write(row)
                except Exception as e:
                    logging.error(f"Error writing the series sensors file: {e}")

            if self.series is not None:
                self.series.update_temperature(self.hold_temperature(data))
                self._refresh_status()

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
        """Block on a message the operator asked for by pressing a button."""
        logging.warning(message)
        QtWidgets.QMessageBox.warning(self, "FrESH", message)

    def _alert(self, message):
        """Report something that happened on its own, without blocking.

        A modal box here would freeze the window -- plot, log and all -- until
        somebody clicked it, which is exactly the wrong thing to do when a
        series has just stopped on its own in the middle of the night.
        """
        logging.error(message)

        box = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Icon.Warning,
                                    "FrESH", message, parent=self)
        box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        box.setModal(False)
        box.show()

    def shutdown(self):
        """Stop every worker and release the hardware."""
        if self.series is not None:
            self.series.stop('the window was closed')
            self.series = None

        if self.picture_timer is not None:
            self.picture_timer.stop()

        if self.video_thread is not None:
            self.video_thread.stop()
            self.video_thread = None

        if self.data_worker is not None:
            # Closes the serial port / releases the DAQ board too.
            self.data_worker.stop()
            self.data_worker = None

        self._detach_cycle_logs()

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
        self.widget.setMaximumBlockCount(2000)  # a 3-day series logs a lot

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
