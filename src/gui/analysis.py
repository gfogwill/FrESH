import logging

from PyQt5 import QtWidgets, uic, QtGui, QtCore
from PyQt5.QtWidgets import QComboBox, QLineEdit, QTextEdit
from functools import partial

import cv2

from src import paths
from src.experiment.experiment import FrESHExperiment, process_sensors_data, calculate_frame_temperatures, \
    calculate_freezing_idxs, calculate_freezing_times, calculate_freezing_temps, ExperimentMetadata
from src.gui.experiment_gui import convert_cv_qt

import os
import csv
import pathlib
import numpy as np
from datetime import datetime

rotation_dict = {'-': None,
                 '90 CCW': cv2.ROTATE_90_COUNTERCLOCKWISE,
                 '90 CW': cv2.ROTATE_90_CLOCKWISE,
                 '180': cv2.ROTATE_180}


def copy_to_clipboard_linux(text):
    command = 'echo -n "' + text + '" | xclip -selection clipboard'
    os.system(command)


class ExperimentAnalysisUi(QtWidgets.QMainWindow):
    def __init__(self, *args, **kwargs):
        super(ExperimentAnalysisUi, self).__init__(*args, **kwargs)

        self.metadata_modified = False  # Flag to track if metadata has been modified

        self.experiment = None

        self.selected_droplet = None
        self.grayscales_evolution = None
        self.del_indx = []
        self.t = []
        self.ff = []
        self.frame_t = []

        self.template_img = None

        uic.loadUi('analysis.ui', self)

        self.experiment_list_view = self.findChild(QtWidgets.QListView, 'experimentListView')
        self.model = QtGui.QStandardItemModel(self.experiment_list_view)
        self.experiment_list_view.setModel(self.model)

        self.filter_line_edit = self.findChild(QtWidgets.QLineEdit, 'filter_line_edit')
        self.filter_line_edit.textChanged.connect(self.filter_exp_names)

        self.button_load_experiment = self.findChild(QtWidgets.QPushButton, 'loadExperimentButton')
        self.button_load_experiment.clicked.connect(self.load_experiment)

        # List of attribute names
        attribute_names = [
            "station", "label", "sampler_id",
            "sampler_status", "filter_position", "air_volume", "start_time", "end_time", "v_drop"
        ]

        # Generate lines for finding child widgets
        for attribute_name in attribute_names:
            setattr(self, f"{attribute_name}_text_edit", self.findChild(QtWidgets.QLineEdit, f'{attribute_name}_text_edit'))

        # Connect textChanged signals to update_metadata_modified method
        for attribute_name in attribute_names:
            widget = getattr(self, f"{attribute_name}_text_edit")
            # widget.textChanged.connect(lambda value, attr_name=attribute_name: self.update_metadata(attr_name, value))
            widget.textChanged.connect(lambda: self.show_metadata_alert)

        self.type_combobox = self.findChild(QtWidgets.QComboBox, 'comboBox_type')
        self.type_combobox.currentTextChanged.connect(lambda value, attr_name='experiment_type': self.update_metadata(attr_name, value))

        self.exp_description_line_edit = self.findChild(QtWidgets.QTextEdit, "exp_description_text_edit")
        self.exp_description_line_edit.textChanged.connect(self.show_metadata_alert)

        # ToDo: put in another place the code
        self.button_run_analysis = self.findChild(QtWidgets.QPushButton, 'runButton')
        self.button_run_analysis.clicked.connect(self.run_analysis)

        # self.button_detect = self.findChild(QtWidgets.QPushButton, "pushButton_Detect")
        # self.button_detect.clicked.connect(self.detect_circles)

        # self.button_detect = self.findChild(QtWidgets.QPushButton, "pushButton_Lock")
        # self.button_detect.clicked.connect(self.lock_circles)

        self.button_save = self.findChild(QtWidgets.QPushButton, 'saveButton')
        self.button_save.clicked.connect(self.save)

        self.spinbox_delete = self.findChild(QtWidgets.QSpinBox, 'delete_spinbox')

        self.button_delete = self.findChild(QtWidgets.QPushButton, 'deleteDropletButton')
        self.button_delete.clicked.connect(self.delete_indx)

        self.button_scan_start = self.findChild(QtWidgets.QPushButton, 'set_scan_start_button')
        self.button_scan_start.clicked.connect(self.update_scan_start)

        self.button_scan_end = self.findChild(QtWidgets.QPushButton, 'set_scan_end_button')
        self.button_scan_end.clicked.connect(self.update_scan_end)

        self.label_deleted = self.findChild(QtWidgets.QLabel, 'deleted_label')

        self.image_frame = self.findChild(QtWidgets.QLabel, 'img_label')
        self.image_frame.setScaledContents(True)

        self.templates_combobox = self.findChild(QtWidgets.QComboBox, 'comboBox_templates')
        self.populate_combobox_templates()
        self.templates_combobox.currentTextChanged.connect(self.update_template_img)

        self.label_temp = self.findChild(QtWidgets.QLabel, 'temp_label')

        self.rotation_combobox = self.findChild(QtWidgets.QComboBox, 'comboBox_rotation')
        self.rotation_combobox.currentTextChanged.connect(self.update_rotation)

        self.horizontalSlider_13.valueChanged['int'].connect(lambda value: self.update_hough_dict_param("min_distance", value))
        self.horizontalSlider_14.valueChanged['int'].connect(lambda value: self.update_hough_dict_param("param1", value))
        self.horizontalSlider_15.valueChanged['int'].connect(lambda value: self.update_hough_dict_param("param2", value))
        self.horizontalSlider_16.valueChanged['int'].connect(lambda value: self.update_hough_dict_param("min_radius", value))
        self.horizontalSlider_17.valueChanged['int'].connect(lambda value: self.update_hough_dict_param("max_radius", value))

        self.framesSlider.valueChanged['int'].connect(self.update_img)

        self.attribute_to_widget_mapping = {
            "label": self.label_text_edit,
            "experiment_type": self.experiment_type_text_edit,
            "start_time": self.start_time_text_edit,
            "end_time": self.end_time_text_edit,
            "station": self.station_text_edit,
            "sampler_id": self.sampler_id_text_edit,
            "sampler_status": self.sampler_status_text_edit,
            "filter_position": self.filter_position_text_edit,
            "air_volume": self.air_volume_text_edit,

            "flow": self.flow_text_edit,
            "temp": self.temp_text_edit,
            "press": self.press_text_edit,
            "exp_description": self.exp_description_text_edit,

            "template_img": self.templates_combobox,
            "v_drop": self.v_drop_text_edit,
            "filter_fraction": self.filter_fraction_text_edit,
            "v_wash": self.wash_vol_text_edit,
            "dil_factor": self.dil_factor_text_edit,

        }

        self.FFwidget.setLabel('left', 'Frozen Fraction', color='red', size=30)

        self.image_frame.mousePressEvent = self.mouse_clicked

        self.populate_experiment_list()

    def load_metadata_from_gui(self):
        # metadata = ExperimentMetadata()  # Assuming ExperimentMetadata is a class to hold metadata

        # Load metadata from text edits
        for attribute_name, widget in self.attribute_to_widget_mapping.items():
            if widget is None:
                continue

            if isinstance(widget, QComboBox):
                value = widget.currentText()
            elif isinstance(widget, (QLineEdit, QTextEdit)):
                value = widget.toPlainText() if isinstance(widget, QTextEdit) else widget.text()
            else:
                continue

            # Special handling for date and time attributes
            if attribute_name.endswith("_time"):
                value = datetime.strptime(value, "%Y-%m-%d %H:%M") if value else None

            setattr(self.experiment.metadata, attribute_name, value)

        return self.experiment.metadata

    def update_metadata_description(self):
        self.update_metadata('exp_description', self.exp_description_line_edit.toPlainText())

    def update_scan_start(self):
        frame = self.framesSlider.value()

        self.experiment.metadata.scan_start_timestamp = str(self.experiment.img_files[frame].stem)
        self.experiment.save_metadata_to_file()
        self.load_experiment()

    def update_scan_end(self):
        frame = self.framesSlider.value()

        self.experiment.metadata.scan_end_timestamp = str(self.experiment.img_files[frame].stem)
        self.experiment.save_metadata_to_file()
        self.load_experiment()

    def load_metadata_into_gui(self, metadata):

        # Load metadata into text edits
        for attribute_name, widget in self.attribute_to_widget_mapping.items():
            if widget is None:
                continue
            if hasattr(metadata, attribute_name):
                value = getattr(metadata, attribute_name)

                # Special handling for date and time attributes
                if attribute_name.endswith("_time") and isinstance(value, datetime):
                    value = value.strftime("%Y-%m-%d %H:%M") if value else ""

                # Update the widgets
                if isinstance(widget, QComboBox):
                    # Check if the value is already in the combo box items
                    found = False
                    for index in range(widget.count()):
                        if widget.itemText(index) == str(value):
                            widget.setCurrentIndex(index)
                            found = True
                            break

                    # If the value is not found, add it as a new item
                    if not found:
                        widget.addItem(str(value))
                        widget.setCurrentText(str(value))

                    # Connect QComboBox signal
                    widget.currentTextChanged.connect(
                    lambda value=value, attribute_name=attribute_name: self.update_metadata(attribute_name, value))

                #elif isinstance(widget, QLineEdit) or isinstance(widget, QTextEdit):
                else:
                    widget.setText(str(value))
                    # Connect QLineEdit signal
                    widget.textChanged.connect(
                        lambda text=value, attribute_name=attribute_name: self.update_metadata(attribute_name, text))

    def update_metadata(self, attribute_name, new_value):
        # logging.debug(print("Updating metadata:", attribute_name, new_value))

        # Update the corresponding attribute in the metadata object
        metadata = self.experiment.metadata

        if hasattr(metadata, attribute_name):
            # Special handling for date and time attributes
            # if attribute_name.endswith("_time"):
            #     new_value = datetime.strptime(new_value, "%Y-%m-%d %H:%M") if new_value else None

            setattr(metadata, attribute_name, new_value)
            self.show_metadata_alert()

    def populate_combobox_templates(self):
        png_files = [file for file in os.listdir(paths.etc_path) if file.endswith(".png")]
        self.templates_combobox.addItems(png_files)
        self.template_img = self.templates_combobox.currentText()

    def update_template_img(self):
        template_img = self.templates_combobox.currentText()

        self.experiment.metadata.template_img = template_img
        self.show_metadata_alert()

        template_image = cv2.imread(str(paths.etc_path / template_img))

        self.image_frame.setFixedWidth(template_image.shape[1])
        self.image_frame.setFixedHeight(template_image.shape[0])

        self.update_img()

    def update_rotation(self):
        rotation = self.rotation_combobox.currentText()

        self.experiment.metadata.rotation = rotation_dict[rotation]
        self.show_metadata_alert()
        self.update_img()

    def run_analysis(self):
        self.experiment.run_analysis()

        frame = self.framesSlider.value()

        if self.experiment.is_analyzed:
            self.FFwidget.clear()
            self.FFwidget.plot(self.experiment.t, self.experiment.ff)
            self.FFwidget.plot([self.frame_t[frame], self.frame_t[frame]], self.FFwidget.getAxis('left').range)

    def populate_experiment_list(self):
        # Clear the model
        self.model.clear()

        # Load and display exp_names
        listdir = os.listdir(paths.raw_data_path)
        listdir.sort(reverse=True)

        for exp_name in listdir:
            item = QtGui.QStandardItem(exp_name)
            item.setEditable(False)
            self.model.appendRow(item)

    def update_hough_dict_param(self, param_name, new_value):
        self.experiment.metadata.hough_params[param_name] = new_value
        self.experiment.detect_circles()
        self.show_metadata_alert()

    def mouse_clicked(self, evt):
        x = evt.pos().x()
        y = evt.pos().y()

        frame = self.framesSlider.value()

        if hasattr(self.experiment, "circles_positions"):
            self.selected_droplet = np.argmin(np.linalg.norm(self.experiment.circles_positions[:, :2] - np.array([x, y]), axis=1))
            print(f'clicked plot X: {x}, Y: {y}, circle: {self.selected_droplet}')

            self.FFwidget_grayscale.clear()
            self.FFwidget_grayscale.plot(self.frame_t, self.experiment.grayscales_evolution[:, self.selected_droplet])

        self.FFwidget_grayscale.plot([self.frame_t[frame], self.frame_t[frame]], self.FFwidget_grayscale.getAxis('left').range)

    def filter_exp_names(self):
        # Get the filter text
        filter_texts = [filter_text.strip().upper() for filter_text in self.filter_line_edit.text().split('&')]
        # Clear the model
        self.model.clear()

        # Load and display filtered exp_names
        listdir = os.listdir(paths.raw_data_path)
        listdir.sort(reverse=True)

        for exp_name in listdir:
            if all(filter_text in exp_name.upper() for filter_text in filter_texts):
                item = QtGui.QStandardItem(exp_name)
                item.setEditable(False)
                self.model.appendRow(item)

    def delete_indx(self):
        value = self.spinbox_delete.value()
        if value in self.del_indx:
            self.del_indx.remove(value)
        else:
            self.del_indx.append(value)
        self.label_deleted.setText("Delete droplets : " + str(self.del_indx))

    def save(self):
        i = pathlib.Path(paths.interim_data_path / self.exp_name)
        i.mkdir(parents=True, exist_ok=True)

        self.experiment.metadata = self.load_metadata_from_gui()

        self.experiment.save_metadata_to_file()

        # Save metadata to a file
        if self.metadata_modified:
            self.metadata_modified = False
            self.hide_metadata_alert()

        p = pathlib.Path(paths.processed_data_path / self.exp_name)
        p.mkdir(parents=True, exist_ok=True)

        if self.experiment.is_analyzed:
            with open(paths.processed_data_path / self.exp_name / 'report.csv', 'w') as fo:
                fo.write(f'index, temp, ff, conc_per_L, conc_per_drop\n')
                for i in range(len(self.experiment.t)):
                    fo.write(f'{i}, {self.experiment.t[i]}, {self.experiment.ff[i]}, {self.experiment.conc_per_L[i]}, '
                             f'{self.experiment.conc_per_drop[i]} \n')

            with open(paths.interim_data_path / self.exp_name / 'freezing_temps.csv', 'w', newline='') as csv_file:
                csv_writer = csv.writer(csv_file)
                csv_writer.writerow(['Index', 'Temperature'])
                csv_writer.writerows(zip(*[iter(self.experiment.freezing_temps)] * 2))  # Group data into pairs

    def show_metadata_alert(self):
        # Show an alert to inform the user that metadata has been modified
        self.metadata_modified = True
        self.setWindowTitle(self.exp_name + "*")

    def hide_metadata_alert(self):
        # Hide the metadata modification alert
        self.metadata_modified = False
        self.setWindowTitle(self.exp_name)

    def update_img(self):
        frame = self.framesSlider.value()

        self.frameNumber.setText('Image: ' + str(self.experiment.img_files[frame].stem))
        self.label_temp.setText('Temperature: ' + str(self.frame_t[frame]))

        img = self.experiment.get_img(frame, self.selected_droplet)

        qt_img = convert_cv_qt(img)
        self.image_frame.setPixmap(qt_img)

        if self.experiment.is_analyzed:
            self.FFwidget.clear()
            self.FFwidget.plot(self.experiment.t, self.experiment.ff)
            self.FFwidget.plot([self.frame_t[frame], self.frame_t[frame]], self.FFwidget.getAxis('left').range)

        if hasattr(self.experiment, "circles_positions") and self.selected_droplet is not None:
            self.FFwidget_grayscale.clear()
            self.FFwidget_grayscale.plot(self.frame_t, self.experiment.grayscales_evolution[:, self.selected_droplet])
            self.FFwidget_grayscale.plot([self.frame_t[frame], self.frame_t[frame]],
                                     self.FFwidget_grayscale.getAxis('left').range)

    def load_experiment(self):
        self.selected_droplet = None
        self.exp_name = self.experiment_list_view.currentIndex().data()
        copy_to_clipboard_linux(self.exp_name)
        self.setWindowTitle(self.exp_name)

        self.experiment = FrESHExperiment(self.exp_name)

        self.framesSlider.setValue(0)
        self.framesSlider.setMaximum(self.experiment.img_files.__len__() - 1)
        self.frame_t = calculate_frame_temperatures(self.experiment.img_files, self.exp_name)

        self.load_metadata_into_gui(self.experiment.metadata)

        self.experiment.detect_circles()

        img = self.experiment.get_img(0)

        qt_img = convert_cv_qt(img)

        self.image_frame.setPixmap(qt_img)

        # self.run_analysis()
        self.update_img()
        self.hide_metadata_alert()

        if not self.experiment.is_analyzed:
            self.experiment.run_analysis()
            if self.experiment.is_analyzed:
                self.FFwidget.clear()
                self.FFwidget.plot(self.experiment.t, self.experiment.ff)
                self.FFwidget.plot([self.frame_t[0], self.frame_t[0]], self.FFwidget.getAxis('left').range)
        # next_index = self.experiment_list_view.currentIndex().row() + 1
        # self.experiment_list_view.setCurrentIndex(self.experiment_list_view.model().index(next_index, 0))

