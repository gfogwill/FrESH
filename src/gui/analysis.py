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

        uic.loadUi('analysis.ui', self)

        self.experiment_list_view = self.findChild(QtWidgets.QListView, 'experimentListView')

        self.button_load_experiment = self.findChild(QtWidgets.QPushButton, 'loadExperimentButton')
        self.button_load_experiment.clicked.connect(self.load_experiment)

        self.button_run_analysis = self.findChild(QtWidgets.QPushButton, 'runButton')
        self.button_run_analysis.clicked.connect(self.run_analysis)

        self.button_save = self.findChild(QtWidgets.QPushButton, 'saveButton')
        self.button_save.clicked.connect(self.save)

        self.button_detect = self.findChild(QtWidgets.QPushButton, "pushButton_Detect")
        self.button_detect.clicked.connect(self.detect_circles)

        self.button_detect = self.findChild(QtWidgets.QPushButton, "pushButton_Lock")
        self.button_detect.clicked.connect(self.lock_circles)

        self.spinbox_delete = self.findChild(QtWidgets.QSpinBox, 'delete_spinbox')

        self.button_delete = self.findChild(QtWidgets.QPushButton, 'deleteButton')
        self.button_delete.clicked.connect(self.delete_indx)

        self.label_deleted = self.findChild(QtWidgets.QLabel, 'deleted_label')

        self.image_frame = self.findChild(QtWidgets.QLabel, 'img_label')
        self.image_frame.setFixedWidth(600)
        self.image_frame.setFixedHeight(402)
        self.image_frame.setScaledContents(True)

        self.label_temp = self.findChild(QtWidgets.QLabel, 'temp_label')

        self.horizontalSlider_13.valueChanged['int'].connect(self.update_img)
        self.horizontalSlider_14.valueChanged['int'].connect(self.update_img)
        self.horizontalSlider_15.valueChanged['int'].connect(self.update_img)
        self.horizontalSlider_16.valueChanged['int'].connect(self.update_img)
        self.horizontalSlider_17.valueChanged['int'].connect(self.update_img)
        self.framesSlider.valueChanged['int'].connect(self.update_img)

        self.FFwidget.setLabel('left', 'Frozen Fraction', color='red', size=30)

        #self.image_frame.scene().sigMouseClicked.connect(self.mouse_clicked)
        self.image_frame.mousePressEvent = self.mouse_clicked

        model = QtGui.QStandardItemModel()
        self.experiment_list_view.setModel(model)

        listdir = os.listdir(paths.raw_data_path)
        listdir.sort(reverse=True)

        for i in listdir:
            item = QtGui.QStandardItem(i)
            item.setEditable(False)
            model.appendRow(item)

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

#x        img = auto_crop(img)

        img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        self.dcirc = circles.get_circles(gray,
                                         minDist=self.horizontalSlider_13.value(),
                                         param1=self.horizontalSlider_14.value(),
                                         param2=self.horizontalSlider_15.value(),
                                         minRadius=self.horizontalSlider_16.value(),
                                         maxRadius=self.horizontalSlider_17.value(),
                                         sort=True, plot=True)

    def lock_circles(self):
        pass

    def update_img(self):
        frame = self.framesSlider.value()
        self.frameNumber.setText('Image: ' + str(self.img_files[frame].stem))
        self.label_temp.setText('Temperature: ' + str(self.frame_t[frame]))

        img = cv2.imread(str(self.img_files[frame]))
        img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        #img = auto_crop(img)

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

    def run_analysis(self):
        nu = self.experiment.metadata.dil_factor
        v_wash = self.experiment.metadata.v_wash
        v_drop = self.experiment.metadata.v_drop
        v_air = self.experiment.metadata.air_volume
        filter_fraction = self.experiment.metadata.filter_fraction

        minDist = self.horizontalSlider_13.value()
        param1 = self.horizontalSlider_14.value()
        param2 = self.horizontalSlider_15.value()
        minRadius = self.horizontalSlider_16.value()
        maxRadius = self.horizontalSlider_17.value()

        self.grayscales_evolution = self.process_images(self.img_files, minDist, param1, param2, minRadius, maxRadius)
        self.freezing_idxs = calculate_freezing_idxs(self.grayscales_evolution)
        self.del_indx = [i - 1 for i in self.del_indx]
        self.freezing_idxs = np.delete(self.freezing_idxs, self.del_indx)
        freezing_times = calculate_freezing_times(self.img_files, self.freezing_idxs)
        self.t, self.ff = process_sensors_data(self.exp_name, self.freezing_idxs, freezing_times)

        self.FFwidget.clear()
        self.FFwidget.plot(self.t, self.ff)

        # Normalization factor to L^-1
        X = nu * v_wash / (v_air / filter_fraction)

        # Concentration per sample
        self.conc_per_drop = - np.log(1 - np.array(self.ff)) / v_drop
        # Concentration per standar L of air
        self.conc_per_L = self.conc_per_drop * X

        # self.conc = - 1 * 1 * np.log(1 - np.array(self.ff)) / (v_drop * 1 * 1)

    def process_images(self, img_files, minDist, param1, param2, minRadius, maxRadius):
        # function to process the images and return the grayscales
        res = []
        for img_file in img_files:
            img_path = str(img_file)
            img = cv2.imread(img_path)
#            img = auto_crop(img)
            img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
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
        img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        #img = auto_crop(img)

        qt_img = convert_cv_qt(img)
        self.image_frame.setPixmap(qt_img)

        self.framesSlider.setMaximum(self.img_files.__len__() - 1)
        self.frame_t = calculate_frame_temperatures(self.img_files, self.exp_name)

        self.detect_circles()
        self.run_analysis()
        self.update_img()

