import logging

from PyQt5 import QtWidgets, uic, QtGui

import cv2

from src.analysis.circles import auto_crop
from src import paths
from src.analysis import circles
from src.gui.experiment_gui import convert_cv_qt
from src.experiment.experiment import FrESHExperiment, process_sensors_data, calculate_frame_temperatures, \
    calculate_freezing_idxs, calculate_freezing_times

import os
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
        self.img_files = None
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

        self.horizontalSlider_13.valueChanged['int'].connect(lambda value: self.update_dict_param("min_distance", value))
        self.horizontalSlider_14.valueChanged['int'].connect(lambda value: self.update_dict_param("param1", value))
        self.horizontalSlider_15.valueChanged['int'].connect(lambda value: self.update_dict_param("param2", value))
        self.horizontalSlider_16.valueChanged['int'].connect(lambda value: self.update_dict_param("min_radius", value))
        self.horizontalSlider_17.valueChanged['int'].connect(lambda value: self.update_dict_param("max_radius", value))

        self.framesSlider.valueChanged['int'].connect(self.update_img)

        self.FFwidget.setLabel('left', 'Frozen Fraction', color='red', size=30)

        # self.image_frame.scene().sigMouseClicked.connect(self.mouse_clicked)
        self.image_frame.mousePressEvent = self.mouse_clicked

        model = QtGui.QStandardItemModel()
        self.experiment_list_view.setModel(model)

        listdir = os.listdir(paths.raw_data_path)
        listdir.sort(reverse=True)

        for i in listdir:
            item = QtGui.QStandardItem(i)
            item.setEditable(False)
            model.appendRow(item)

    def populate_combobox_templates(self):
        png_files = [file for file in os.listdir(paths.etc_path) if file.endswith(".png")]
        self.templates_combobox.addItems(png_files)
        self.template_img = self.templates_combobox.currentText()
        self.update_template_img()

    def update_template_img(self):
        self.template_img = self.templates_combobox.currentText()
        template_image = cv2.imread(str(paths.etc_path / self.template_img))
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

    def detect_circles(self):
        img = cv2.imread(str(self.img_files[0]))

        img = cv2.rotate(img, rotation_dict[self.rotation_combobox.currentText()])
        img = auto_crop(img, self.template_img)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        self.dcirc = circles.get_circles(gray, **self.hough_params, sort=True, plot=True)


    def lock_circles(self):
        pass

    def update_img(self):
        frame = self.framesSlider.value()
        if self.img_files is None:
            return
        self.frameNumber.setText('Image: ' + str(self.img_files[frame].stem))
        self.label_temp.setText('Temperature: ' + str(self.frame_t[frame]))

        img = cv2.imread(str(self.img_files[frame]))
        img = cv2.rotate(img, rotation_dict[self.rotation_combobox.currentText()])
        img = auto_crop(img, self.template_img)

        if hasattr(self, "dcirc"):
            np_dcirc = np.uint16(np.around(self.dcirc))

            for n, i in enumerate(np_dcirc):
                if self.freezing_idxs[n] > frame:
                    cv2.circle(img, (i[0], i[1]), i[2], (0, 0, 255), 1)
                    cv2.putText(img, "{}".format(n), (i[0], i[1]), cv2.FONT_HERSHEY_PLAIN, 1.0, (255, 255, 0), 1)
                else:
                    cv2.circle(img, (i[0], i[1]), i[2], (0, 255, 0), 1)
                    cv2.putText(img, "{}".format(n), (i[0], i[1]), cv2.FONT_HERSHEY_PLAIN, 1.0, (255, 255, 0), 1)

        # img = circles.add_circles(img, self.dcirc)

        qt_img = convert_cv_qt(img)
        self.image_frame.setPixmap(qt_img)

        self.FFwidget.clear()
        self.FFwidget.plot(self.t, self.ff)
        self.FFwidget.plot([self.frame_t[frame], self.frame_t[frame]], self.FFwidget.getAxis('left').range)

        #self.FFwidget_grayscale.plot([self.frame_t[frame], self.frame_t[frame]], self.FFwidget_grayscale.getAxis('left').range)

    def run_analysis(self):
        nu = self.experiment.metadata.dil_factor
        v_wash = self.experiment.metadata.v_wash
        v_drop = self.experiment.metadata.v_drop
        v_air = self.experiment.metadata.air_volume
        filter_fraction = self.experiment.metadata.filter_fraction

        self.grayscales_evolution = self.process_images(self.img_files)
        self.freezing_idxs = calculate_freezing_idxs(self.grayscales_evolution)

        self.del_indx = [i - 1 for i in self.del_indx]
        self.freezing_idxs = np.delete(self.freezing_idxs, self.del_indx)
        freezing_times = calculate_freezing_times(self.img_files, self.freezing_idxs)

        self.t, self.ff = process_sensors_data(self.exp_name, self.freezing_idxs, freezing_times)

        self.FFwidget.clear()
        self.FFwidget.plot(self.t, self.ff)

        # Normalization factor to L^-1
        X = nu * v_wash / (v_air * filter_fraction)

        # Concentration per sample
        self.conc_per_drop = - np.log(1 - np.array(self.ff)) / v_drop
        # Concentration per standar L of air
        self.conc_per_L = self.conc_per_drop * X

        # self.conc = - 1 * 1 * np.log(1 - np.array(self.ff)) / (v_drop * 1 * 1)

    def process_images(self, img_files):
        # function to process the images and return the grayscales
        res = []

        for img_file in img_files:
            img_path = str(img_file)
            img = cv2.imread(img_path)
            img = cv2.rotate(img, rotation_dict[self.rotation_combobox.currentText()])
            img = auto_crop(img, self.template_img)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # dcirc = circles.get_circles(gray, minDist, param1, param2, minRadius, maxRadius, sort=True, plot=False)

            res.append(circles.get_grayscales(gray, self.dcirc))

            img = circles.add_circles(gray, self.dcirc)

            qt_img = convert_cv_qt(img)
            self.image_frame.setPixmap(qt_img)

        return np.array(res)

    def load_experiment(self):
        self.t = []
        self.ff = []
        self.del_indx = []

        self.exp_name = self.experiment_list_view.currentIndex().data()

        self.setWindowTitle(self.exp_name)

        self.experiment = FrESHExperiment(self.exp_name)

        img_dir = paths.raw_data_path / self.exp_name / 'pics'

        # get a list of all PNG files in the directory
        self.img_files = [f for f in img_dir.iterdir() if f.is_file() and f.suffix == ".jpg"]
        # sort the list of images
        self.img_files.sort()

        if self.img_files.__len__() == 0:
            logging.error(f"No pictures found in dir: {img_dir}")

        img = cv2.imread(str(self.img_files[0]))
        img = cv2.rotate(img, rotation_dict[self.rotation_combobox.currentText()])
        img = auto_crop(img, self.template_img)

        qt_img = convert_cv_qt(img)
        self.image_frame.setPixmap(qt_img)

        self.framesSlider.setMaximum(self.img_files.__len__() - 1)
        self.frame_t = calculate_frame_temperatures(self.img_files, self.exp_name)

        self.detect_circles()
        self.run_analysis()
        self.update_img()

        next_index = self.experiment_list_view.currentIndex().row() + 1
        self.experiment_list_view.setCurrentIndex(self.experiment_list_view.model().index(next_index, 0))



