from PyQt5 import QtWidgets, uic, QtGui

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *

import cv2

from src import paths
from src.analysis import circles
from src.gui.experiment_gui import convert_cv_qt

import os
import numpy as np
from datetime import datetime
import pyqtgraph as pg


def get_exp_description(exp_name):
    with open(src.paths.raw_data_path / exp_name / f"EX{exp_name.split('_')[0]}.log", "r") as f:
        lines = f.readlines()
        for line in lines:
            if "exp_description" in line:
                return line
    return None


def calculate_freezing_idxs(grayscales_evolution):
    # function to calculate the freezing indices
    freezing_idxs = []
    for i in range(grayscales_evolution.shape[-1]):
        grayscales_diffs = [s - t for s, t in zip(grayscales_evolution[:, i], grayscales_evolution[1:, i])]
        freezing_idxs.append(np.argmax(grayscales_diffs) + 1)
    return freezing_idxs


def calculate_freezing_times(img_files, freezing_idxs):
    # function to calculate the freezing times
    freezing_times = []
    for i, idx in enumerate(freezing_idxs):
        freezing_times.append(datetime.strptime(img_files[freezing_idxs[i]].stem, "%Y%m%d%H%M%S"))
    return np.array(freezing_times)


def process_sensors_data(exp_name, freezing_idxs, freezing_times):
    # function to process the sensors data and return the t and ff arrays
    str2date = lambda x: datetime.strptime(x.decode("utf-8"), '%Y-%m-%d %H:%M:%S')
    data = np.genfromtxt(paths.raw_data_path / exp_name / 'sensors_data.csv',
                         delimiter=',',
                         dtype=None,
                         names=True,
                         converters={0: str2date})

    t = []
    ff = []

    for i, line in enumerate(data):
        t.append(line[2])
        ff.append((freezing_times <= line['datetime']).sum() / freezing_idxs.__len__())

    return t, ff


class ExperimentAnalysisUi(QtWidgets.QMainWindow):
    def __init__(self, *args, **kwargs):
        super(ExperimentAnalysisUi, self).__init__(*args, **kwargs)

        self.exp_name = None
        self.img_files = None
        self.line1 = None
        self.ff = []

        uic.loadUi('analysis.ui', self)

        self.experiment_list_view = self.findChild(QtWidgets.QListView, 'experimentListView')

        self.button_load_experiment = self.findChild(QtWidgets.QPushButton, 'loadExperimentButton')
        self.button_load_experiment.clicked.connect(self.load_experiment)

        self.button_run_analysis = self.findChild(QtWidgets.QPushButton, 'runButton')
        self.button_run_analysis.clicked.connect(self.run_analysis)

        self.button_save = self.findChild(QtWidgets.QPushButton, 'saveButton')
        self.button_save.clicked.connect(self.save)

        self.image_frame = self.findChild(QtWidgets.QLabel, 'img_label')

        self.horizontalSlider_13.valueChanged['int'].connect(self.update_img)
        self.horizontalSlider_14.valueChanged['int'].connect(self.update_img)
        self.horizontalSlider_15.valueChanged['int'].connect(self.update_img)
        self.horizontalSlider_16.valueChanged['int'].connect(self.update_img)
        self.horizontalSlider_17.valueChanged['int'].connect(self.update_img)
        self.framesSlider.valueChanged['int'].connect(self.update_img)

        self.FFwidget.setLabel('left', 'Frozen Fraction', color='red', size=30)

        model = QtGui.QStandardItemModel()
        self.experiment_list_view.setModel(model)

        listdir = os.listdir(paths.raw_data_path)
        listdir.sort(reverse=True)

        for i in listdir:
            item = QtGui.QStandardItem(i)
            item.setEditable(False)
            model.appendRow(item)

    def save(self):
        pass

    def update_img(self):
        frame = self.framesSlider.value()
        img = cv2.imread(str(self.img_files[frame]))

        img = self.auto_crop(img)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        dcirc = circles.get_circles(gray,
                                    minDist=self.horizontalSlider_13.value(),
                                    param1=self.horizontalSlider_14.value(),
                                    param2=self.horizontalSlider_15.value(),
                                    minRadius=self.horizontalSlider_16.value(),
                                    maxRadius=self.horizontalSlider_17.value(),
                                    sort=True, plot=False)

        img = circles.add_circles(img, dcirc)

        qt_img = convert_cv_qt(img)
        self.image_frame.setPixmap(qt_img)

    def run_analysis(self):
        minDist = self.horizontalSlider_13.value()
        param1 = self.horizontalSlider_14.value()
        param2 = self.horizontalSlider_15.value()
        minRadius = self.horizontalSlider_16.value()
        maxRadius = self.horizontalSlider_17.value()

        grayscales_evolution = self.process_images(self.img_files, minDist, param1, param2, minRadius, maxRadius)
        freezing_idxs = calculate_freezing_idxs(grayscales_evolution)
        freezing_times = calculate_freezing_times(self.img_files, freezing_idxs)
        t, ff = process_sensors_data(self.exp_name, freezing_idxs, freezing_times)

        self.FFwidget.clear()
        self.FFwidget.plot(t, ff)

    def process_images(self, img_files, minDist, param1, param2, minRadius, maxRadius):
        # function to process the images and return the grayscales
        res = []
        for img_file in img_files:
            img_path = str(img_file)
            img = cv2.imread(img_path)
            img = self.auto_crop(img)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            dcirc = circles.get_circles(gray, minDist, param1, param2, minRadius, maxRadius, sort=True, plot=False)
            res.append(circles.get_grayscales(gray, dcirc))

            img = circles.add_circles(gray, dcirc)

            qt_img = convert_cv_qt(img)
            self.image_frame.setPixmap(qt_img)

        return np.array(res)

    def load_experiment(self):
        self.exp_name = self.experiment_list_view.currentIndex().data()

        img_dir = paths.raw_data_path / self.exp_name / 'pics'

        # get a list of all PNG files in the directory
        self.img_files = [f for f in img_dir.iterdir() if f.is_file() and f.suffix == ".png"]

        # sort the list of images
        self.img_files.sort()

        img = cv2.imread(str(self.img_files[0]))

        img = self.auto_crop(img)

        qt_img = convert_cv_qt(img)
        self.image_frame.setPixmap(qt_img)

        self.framesSlider.setMaximum(self.img_files.__len__() - 1)

    @staticmethod
    def auto_crop(img):
        template_image = cv2.imread(str(paths.etc_path / 'template_image.png'))

        # Get the height and width of the template image
        template_height, template_width = template_image.shape[:2]

        # Perform template matching
        match_result = cv2.matchTemplate(img, template_image, cv2.TM_CCOEFF_NORMED)

        # Get the location of the best match
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(match_result)

        # Calculate the top-left and bottom-right coordinates of the ROI
        top_left = max_loc
        bottom_right = (top_left[0] + template_width, top_left[1] + template_height)

        # Draw a rectangle around the ROI
        # cv2.rectangle(img, top_left, bottom_right, (0, 0, 255), 2)
        cropper_img = img[top_left[1]:bottom_right[1], top_left[0]:bottom_right[0]]

        return cropper_img
