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

stations_dict = {'Water background': 'WBG',
                 'Helsinki': 'HEL',
                 'Utö': 'UTO',
                 'Kuopio': 'KUO',
                 'Pallas': 'PAL'}


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
        values = input_str.split(";")

        start_date = datetime.strptime(values[2], "%d.%m.%y")
        end_date = datetime.strptime(values[4], "%d.%m.%y")

        station = stations_dict[self.comboBoxStation.currentText()]

        label = f"{station}_{start_date.strftime('%Y%m%d')}"
        # Assign each value to the corresponding key in a dictionary
        metadata = {
            "station": values[0],
            "sampling_time": 24,
            "sampling_interval": 10,
            "storage_temperature": -20,
            "experiment_type": "Filter",
            "label": f"{label}",
            "sampler_ID": "",
            "air_volume": float(values[8]),
            "start_time": f"{start_date} {values[3]}",
            "end_time": f"{end_date} {values[5]}",
            "temp": "",
            "press": "",
            "exp_description": "",
            "run": 0,
            "v_drop": 5e-05,
            "v_wash": 0.01,
            "dil_factor": 1,
            "filter_fraction": 1
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
        self.textFilterFraction.setPlainText(str(metadata["filter_fraction"]))

    def read_metadata(self):

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
