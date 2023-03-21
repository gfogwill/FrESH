import PyQt5
from PyQt5 import QtGui, QtWidgets, uic, QtCore
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import QTimer, pyqtSlot, Qt
from PyQt5.QtWidgets import *

import sys
import time
from datetime import datetime

from experiment_gui import ExperimentUi
from src.experiment.experiment import FrESHExperiment, ExperimentMetadata
from src import paths


class ExperimentMetadataUi(QtWidgets.QMainWindow):
    def __init__(self, *args, **kwargs):
        super(ExperimentMetadataUi, self).__init__(*args, **kwargs)

        uic.loadUi('experiment_metadata.ui', self)

        self.experiment = None

        self.button_confirm = self.findChild(QtWidgets.QDialogButtonBox, 'ConfirmbuttonBox')
        self.button_confirm.accepted.connect(self.start_experiment)
        # self.button_confirm.rejected.connect()

        self.metadata_string = self.findChild(QtWidgets.QPlainTextEdit, 'plainTextMetadata')
        self.metadata_string.textChanged.connect(self.parse_string)

    def parse_string(self):
        input_str = self.metadata_string.toPlainText() # "HEL/Z09/20220218/16.6/72,2/17/2022,23:59,2/20/2022,23.59,60.20,24.96,62892.6,Z09,0.2"

        if input_str.__len__() == 0:
            return

        # Split the input string by "/"
        cols = input_str.split(",")
        values = cols[0].split("/")

        start_date = datetime.strptime(cols[1], "%m/%d/%Y").strftime("%Y-%m-%d")
        end_date = datetime.strptime(cols[3], "%m/%d/%Y").strftime("%Y-%m-%d")

        # Assign each value to the corresponding key in a dictionary
        metadata = {
            "station": values[0],
            "sampling_time": int(values[4]),
            "sampling_interval": 10,
            "storage_temperature": -20,
            "experiment_type": "Filter",
            "label": f"{values[0]}_{values[1]}_{values[2]}",
            "sampler_ID": values[1],
            "air_volume": float(cols[7]),
            "start_time": f"{start_date} {cols[2]}",
            "end_time": f"{end_date} {cols[4]}",
            "temp": "",
            "press": "",
            "exp_description": "",
            "run": 0,
            "v_drop": 5e-05,
            "v_wash": 0.01,
            "dil_factor": 1
        }

        #self.comboBoxSampleType.setPlainText(metadata["experiment_type"])
        #self.comboBoxStation.setPlainText(metadata["station"])

        self.textLabel.setPlainText(metadata["label"])
        self.textSamplerID.setPlainText(metadata["sampler_ID"])
        self.textAirVolume.setPlainText(str(metadata["air_volume"]))
        self.textStartTime.setPlainText(metadata["start_time"])
        self.textEndTime.setPlainText(metadata["end_time"])
        self.textTemp.setPlainText(metadata["temp"])
        self.textPress.setPlainText(metadata["press"])
        self.textDescription.setPlainText(metadata["exp_description"])
        self.textVolWash.setPlainText(str(metadata["v_wash"]))
        self.textDilFactor.setPlainText(str(metadata["dil_factor"]))

    def read_metadata(self):
        stations_dict = {'Water background': 'WBG',
                         'Helsinki': 'HEL',
                         'Utö': 'UTO',
                         'Kuopio': 'KUO',
                         'Pallas': 'PAL'}

        # self.exp_metadata = dict(type=self.comboBoxSampleType.currentText(),
        #                          station=stations_dict[self.comboBoxStation.currentText()],
        #                          label=self.textLabel.toPlainText(),
        #                          sampler_ID=self.textSamplerID.toPlainText(),
        #                          air_volume=self.textAirVolume.toPlainText(),
        #                          start_time=self.textStartTime.toPlainText(),
        #                          end_time=self.textEndTime.toPlainText(),
        #                          temp=self.textTemp.toPlainText(),
        #                          press=self.textPress.toPlainText(),
        #                          exp_description=self.textDescription.toPlainText(),
        #                          run=0)

        exp_metadata = ExperimentMetadata(experiment_type=self.comboBoxSampleType.currentText(),
                                          station=stations_dict[self.comboBoxStation.currentText()],
                                          label=self.textLabel.toPlainText(),
                                          sampler_ID=self.textSamplerID.toPlainText(),
                                          air_volume=float(self.textAirVolume.toPlainText()),
                                          start_time=self.textStartTime.toPlainText(),
                                          end_time=self.textEndTime.toPlainText(),
                                          temp=self.textTemp.toPlainText(),
                                          press=self.textPress.toPlainText(),
                                          exp_description=self.textDescription.toPlainText(),
                                          run=0,
                                          v_drop=50e-6,
                                          v_wash=float(self.textVolWash.toPlainText()),
                                          dil_factor=float(self.textDilFactor.toPlainText()))

        exp_metadata.check_required_fields()

        date_str = time.strftime('%Y%m%d%H%M', time.localtime())
        exp_name = paths.raw_data_path / f"{date_str}_{exp_metadata.label}"

        self.experiment = FrESHExperiment(exp_name)
        self.experiment.set_metadata(exp_metadata)

    def start_experiment(self):
        self.read_metadata()
        self.hide()

        self.ExperimentUi = ExperimentUi(self.experiment)
        self.ExperimentUi.show()
