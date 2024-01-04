import logging

from PyQt5 import QtWidgets, uic, QtGui


import cv2

from src import paths
from src.analysis import circles
from src.gui.experiment_gui import convert_cv_qt
from src.experiment.experiment import FrESHExperiment, process_sensors_data, calculate_frame_temperatures, \
    calculate_freezing_idxs, calculate_freezing_times, calculate_freezing_temps

import os
import csv
import pathlib
import numpy as np

rotation_dict = {'-': None,
                 '90 CCW': cv2.ROTATE_90_COUNTERCLOCKWISE,
                 '90 CW': cv2.ROTATE_90_CLOCKWISE,
                 '180': cv2.ROTATE_180}


class ExperimentAnalysisUi(QtWidgets.QMainWindow):
    def __init__(self, *args, **kwargs):
        super(ExperimentAnalysisUi, self).__init__(*args, **kwargs)

        self.conc = None
        self.exp_name = None

        self.experiment = None

        self.selected_droplet = None
        self.grayscales_evolution = None
        self.del_indx = []
        self.t = []
        self.ff = []
        self.frame_t = []

        self.template_img = None

        self.hough_params = {
            "min_distance": 24,
            "param1": 150,
            "param2": 15,
            "min_radius": 13,
            "max_radius": 15}

        uic.loadUi('analysis.ui', self)

        self.experiment_list_view = self.findChild(QtWidgets.QListView, 'experimentListView')
        self.model = QtGui.QStandardItemModel(self.experiment_list_view)
        self.experiment_list_view.setModel(self.model)

        self.filter_line_edit = self.findChild(QtWidgets.QLineEdit, 'filter_line_edit')
        self.filter_line_edit.textChanged.connect(self.filter_exp_names)

        self.button_load_experiment = self.findChild(QtWidgets.QPushButton, 'loadExperimentButton')
        self.button_load_experiment.clicked.connect(self.load_experiment)

        # ToDo: put in another place the code
        # self.button_run_analysis = self.findChild(QtWidgets.QPushButton, 'runButton')
        # self.button_run_analysis.clicked.connect(self.run_analysis)

        # self.button_detect = self.findChild(QtWidgets.QPushButton, "pushButton_Detect")
        # self.button_detect.clicked.connect(self.detect_circles)

        # self.button_detect = self.findChild(QtWidgets.QPushButton, "pushButton_Lock")
        # self.button_detect.clicked.connect(self.lock_circles)

        self.button_save = self.findChild(QtWidgets.QPushButton, 'saveButton')
        self.button_save.clicked.connect(self.save)

        self.spinbox_delete = self.findChild(QtWidgets.QSpinBox, 'delete_spinbox')

        self.button_delete = self.findChild(QtWidgets.QPushButton, 'deleteDropletButton')
        self.button_delete.clicked.connect(self.delete_indx)

        self.label_deleted = self.findChild(QtWidgets.QLabel, 'deleted_label')

        self.image_frame = self.findChild(QtWidgets.QLabel, 'img_label')
        self.image_frame.setScaledContents(True)

        self.templates_combobox = self.findChild(QtWidgets.QComboBox, 'comboBox_templates')
        self.populate_combobox_templates()
        self.templates_combobox.currentTextChanged.connect(self.update_template_img)

        self.label_temp = self.findChild(QtWidgets.QLabel, 'temp_label')

        self.rotation_combobox = self.findChild(QtWidgets.QComboBox, 'comboBox_rotation')
        self.rotation_combobox.currentTextChanged.connect(self.update_rotation)

        self.horizontalSlider_13.valueChanged['int'].connect(lambda value: self.update_dict_param("min_distance", value))
        self.horizontalSlider_14.valueChanged['int'].connect(lambda value: self.update_dict_param("param1", value))
        self.horizontalSlider_15.valueChanged['int'].connect(lambda value: self.update_dict_param("param2", value))
        self.horizontalSlider_16.valueChanged['int'].connect(lambda value: self.update_dict_param("min_radius", value))
        self.horizontalSlider_17.valueChanged['int'].connect(lambda value: self.update_dict_param("max_radius", value))

        self.framesSlider.valueChanged['int'].connect(self.update_img)

        self.FFwidget.setLabel('left', 'Frozen Fraction', color='red', size=30)

        self.image_frame.mousePressEvent = self.mouse_clicked

        self.load_exp_names()

    def load_exp_names(self):
        # Clear the model
        self.model.clear()

        # Load and display exp_names
        listdir = os.listdir(paths.raw_data_path)
        listdir.sort(reverse=True)

        for exp_name in listdir:
            item = QtGui.QStandardItem(exp_name)
            item.setEditable(False)
            self.model.appendRow(item)

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

    def populate_combobox_templates(self):
        png_files = [file for file in os.listdir(paths.etc_path) if file.endswith(".png")]
        self.templates_combobox.addItems(png_files)
        self.template_img = self.templates_combobox.currentText()
        #self.update_template_img()

    def update_rotation(self):
        rotation = self.rotation_combobox.currentText()
        self.experiment.metadata.rotation = rotation_dict[rotation]

    def update_template_img(self):
        template_img = self.templates_combobox.currentText()

        self.experiment.metadata.template_img = template_img

        template_image = cv2.imread(str(paths.etc_path / template_img))

        self.image_frame.setFixedWidth(template_image.shape[1])
        self.image_frame.setFixedHeight(template_image.shape[0])

    def update_dict_param(self, param_name, new_value):
        self.hough_params[param_name] = new_value

    def mouse_clicked(self, evt):
        x = evt.pos().x()
        y = evt.pos().y()
        self.selected_droplet = np.argmin(np.linalg.norm(self.dcirc[:, :2] - np.array([x, y]), axis=1))
        print(f'clicked plot X: {x}, Y: {y}, circle: {self.selected_droplet}')

        self.FFwidget_grayscale.clear()
        self.FFwidget_grayscale.plot(self.frame_t, self.grayscales_evolution[:, self.selected_droplet])

    def delete_indx(self):
        value = self.spinbox_delete.value()
        if value in self.del_indx:
            self.del_indx.remove(value)
        else:
            self.del_indx.append(value)
        self.label_deleted.setText("Delete droplets : " + str(self.del_indx))

    def save(self):
        p = pathlib.Path(paths.processed_data_path / self.exp_name)
        p.mkdir(parents=True, exist_ok=True)

        with open(paths.processed_data_path / self.exp_name / 'report.csv', 'w') as fo:
            fo.write(f'index, temp, ff, conc_per_L, conc_per_drop\n')
            for i in range(len(self.t)):
                fo.write(f'{i}, {self.t[i]}, {self.ff[i]}, {self.conc_per_L[i]}, {self.conc_per_drop[i]} \n')

        with open(paths.processed_data_path / self.exp_name / 'freezing_temps.csv', 'w', newline='') as csv_file:
            csv_writer = csv.writer(csv_file)
            csv_writer.writerow(['Index', 'Temperature'])
            csv_writer.writerows(zip(*[iter(self.freezing_temps)] * 2))  # Group data into pairs

    def update_img(self):
        frame = self.framesSlider.value()

        self.frameNumber.setText('Image: ' + str(self.experiment.img_files[frame].stem))
        self.label_temp.setText('Temperature: ' + str(self.frame_t[frame]))

        img = self.experiment.get_img(frame)

        qt_img = convert_cv_qt(img)
        self.image_frame.setPixmap(qt_img)

        self.FFwidget.clear()
        self.FFwidget.plot(self.t, self.ff)
        self.FFwidget.plot([self.frame_t[frame], self.frame_t[frame]], self.FFwidget.getAxis('left').range)

        #self.FFwidget_grayscale.plot([self.frame_t[frame], self.frame_t[frame]], self.FFwidget_grayscale.getAxis('left').range)

    def load_experiment(self):
        self.t = []
        self.ff = []
        self.del_indx = []

        self.exp_name = self.experiment_list_view.currentIndex().data()

        self.setWindowTitle(self.exp_name)

        self.experiment = FrESHExperiment(self.exp_name)

        img = self.experiment.get_img(0)

        qt_img = convert_cv_qt(img)
        self.image_frame.setPixmap(qt_img)

        self.framesSlider.setValue(0)
        self.framesSlider.setMaximum(self.experiment.img_files.__len__() - 1)
        self.frame_t = calculate_frame_temperatures(self.experiment.img_files, self.exp_name)

        # self.run_analysis()
        self.update_img()

        next_index = self.experiment_list_view.currentIndex().row() + 1
        self.experiment_list_view.setCurrentIndex(self.experiment_list_view.model().index(next_index, 0))



