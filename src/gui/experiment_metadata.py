import PyQt5
from PyQt5 import QtGui, QtWidgets, uic, QtCore
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import QTimer, pyqtSlot, Qt
from PyQt5.QtWidgets import *

import sys
import os
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


def find_data_line(directory_path, date):
    date = date.strftime("%d.%m.%y")
    for root, dirs, files in os.walk(directory_path):
        for file_name in files:
            if file_name == "SUM.CSV":
                sum_path = os.path.join(root, file_name)
                with open(sum_path, "r") as file:
                    lines = file.readlines()
                    for line in lines[1:]:
                        fields = line.strip().split(";")
                        if len(fields) > 2 and fields[2].strip() == date.strip():
                            return line.strip()
    return None


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

        self.button_search = self.findChild(QtWidgets.QPushButton, 'searchButton')
        self.button_search.clicked.connect(self.search_metadata)

    def search_metadata(self):
        dict = {'KUO': '77KUOPIO',
                'HEL': '01HELSINKI',
                'PAL': '36PALLAS',
                'UTO': '09UTÖ'}

        label = self.textLabel.toPlainText()
        directory_path = '/home/perezfo/Desktop/tmp/data/'
        date = "24.06.22"

        station_ID = label[0:3]
        date = datetime.strptime(label[3:], "%Y%m%d")

        metadata_str = find_data_line(paths.external_data_path / 'sampler_raw_data' / dict[station_ID], date)
        if metadata_str is not None:
            values = metadata_str.split(";")
            start_time = datetime.strptime(f"{values[2]} {values[3]}", "%d.%m.%y %H:%M")
            end_time = datetime.strptime(f"{values[4]} {values[5]}", "%d.%m.%y %H:%M")

            metadata = {
                "station": label[0:3],
                "storage_temperature": -20,
                "experiment_type": "Filter",
                "label": f"{label}",
                "sampler_ID": "",
                "air_volume": float(values[8]),
                "start_time": datetime.strftime(start_time, "%Y-%m-%d %H:%M"),
                "end_time": datetime.strftime(end_time, "%Y-%m-%d %H:%M"),
                "filter_port": f"{values[7]}",
                "sampler_status": f"{values[1]}",
                "temp": f"{values[10]}",
                "press": f"{values[11]}",
                "exp_description": f"",
                "run": 0,
                "v_drop": 5e-05,
                "v_wash": 0.01,
                "dil_factor": 1,
                "filter_fraction": 1
            }

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

            return metadata

        else:
            return None

    def parse_string(self):
        input_str = self.metadata_string.toPlainText()

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
                                          dil_factor=float(self.textDilFactor.toPlainText()),
                                          filter_fraction=float(self.textFilterFraction.toPlainText()))

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
