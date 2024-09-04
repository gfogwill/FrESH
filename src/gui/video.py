import cv2
import numpy as np
from PyQt6 import QtWidgets, uic


class VideoSettingsUi(QtWidgets.QMainWindow):
    def __init__(self, video_thread, *args, **kwargs):
        super(VideoSettingsUi, self).__init__(*args, **kwargs)

        uic.loadUi('video_settings.ui', self)

        self.video_thread = video_thread

        self.read_current_settings()

        self.horizontalSlider_1.valueChanged['int'].connect(self.update_brightness_value)
        self.horizontalSlider_2.valueChanged['int'].connect(self.update_contrast_value)
        self.horizontalSlider_3.valueChanged['int'].connect(self.update_saturation_value)
        self.horizontalSlider_4.valueChanged['int'].connect(self.update_hue_value)
        self.horizontalSlider_5.valueChanged['int'].connect(self.update_gamma_value)
        self.horizontalSlider_6.valueChanged['int'].connect(self.update_WB_temperature_value)
        self.horizontalSlider_7.valueChanged['int'].connect(self.update_sharpness_value)
        self.horizontalSlider_8.valueChanged['int'].connect(self.update_pan_value)
        self.horizontalSlider_9.valueChanged['int'].connect(self.update_tilt_value)
        self.horizontalSlider_10.valueChanged['int'].connect(self.update_zoom_value)
        self.horizontalSlider_11.valueChanged['int'].connect(self.update_auto_exposure)
        self.horizontalSlider_12.valueChanged['int'].connect(self.update_exposure)

        self.checkBox_auto_WB.toggled.connect(self.update_auto_WB)
        self.checkBox_plotCircles.toggled.connect(self.update_plot_circles)

    def update_auto_WB(self):

        if self.checkBox_auto_WB.isChecked():
            self.video_thread.cap.set(cv2.CAP_PROP_AUTO_WB, 1)
        else:
            self.video_thread.cap.set(cv2.CAP_PROP_AUTO_WB, 0)

    def update_plot_circles(self):
        if self.checkBox_plotCircles.isChecked():
            self.video_thread.plot_circles = True
        else:
            self.video_thread.plot_circles = False

    def read_current_settings(self):
        self.video_thread.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0)

        self.horizontalSlider_1.setValue(int(self.video_thread.cap.get(cv2.CAP_PROP_BRIGHTNESS)))
        self.horizontalSlider_2.setValue(int(self.video_thread.cap.get(cv2.CAP_PROP_CONTRAST)))
        self.horizontalSlider_3.setValue(int(self.video_thread.cap.get(cv2.CAP_PROP_SATURATION)))
        self.horizontalSlider_4.setValue(int(self.video_thread.cap.get(cv2.CAP_PROP_HUE)))
        self.horizontalSlider_5.setValue(int(self.video_thread.cap.get(cv2.CAP_PROP_GAMMA)))
        self.horizontalSlider_6.setValue(int(self.video_thread.cap.get(cv2.CAP_PROP_WB_TEMPERATURE)))
        self.horizontalSlider_7.setValue(int(self.video_thread.cap.get(cv2.CAP_PROP_SHARPNESS)))
        self.horizontalSlider_8.setValue(int(self.video_thread.cap.get(cv2.CAP_PROP_PAN)/1000.0))
        self.horizontalSlider_9.setValue(int(self.video_thread.cap.get(cv2.CAP_PROP_TILT)/1000.0))
        self.horizontalSlider_10.setValue(int(self.video_thread.cap.get(cv2.CAP_PROP_ZOOM)))
        self.horizontalSlider_11.setValue(int(self.video_thread.cap.get(cv2.CAP_PROP_AUTO_EXPOSURE)))
        self.horizontalSlider_12.setValue(int(self.video_thread.cap.get(cv2.CAP_PROP_EXPOSURE)))

    def update_brightness_value(self, value):
        self.video_thread.cap.set(cv2.CAP_PROP_BRIGHTNESS, value)

    def update_contrast_value(self, value):
        self.video_thread.cap.set(cv2.CAP_PROP_CONTRAST, value)

    def update_saturation_value(self, value):
        self.video_thread.cap.set(cv2.CAP_PROP_SATURATION, value)

    def update_hue_value(self, value):
        self.video_thread.cap.set(cv2.CAP_PROP_HUE, value)

    def update_gamma_value(self, value):
        self.video_thread.cap.set(cv2.CAP_PROP_GAMMA, value)

    def update_WB_temperature_value(self, value):
        self.video_thread.cap.set(cv2.CAP_PROP_WB_TEMPERATURE, value)

    def update_sharpness_value(self, value):
        self.video_thread.cap.set(cv2.CAP_PROP_SHARPNESS, value)

    def update_pan_value(self, value):
        self.video_thread.cap.set(cv2.CAP_PROP_PAN, value*1000)

    def update_tilt_value(self, value):
        self.video_thread.cap.set(cv2.CAP_PROP_TILT, value*1000)

    def update_zoom_value(self, value):
        self.video_thread.cap.set(cv2.CAP_PROP_ZOOM, value)

    def update_auto_exposure(self, value):
        self.video_thread.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, value)

    def update_exposure(self, value):
        self.video_thread.cap.set(cv2.CAP_PROP_EXPOSURE, value)
