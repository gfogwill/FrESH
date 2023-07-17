import PyQt5
from PyQt5 import QtGui, QtWidgets, uic, QtCore
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import QTimer, pyqtSlot, Qt
from PyQt5.QtWidgets import *

import sys
import os
import time
import logging

from datetime import datetime

from experiment_gui import ExperimentUi
from src.experiment.experiment import FrESHExperiment, ExperimentMetadata
from src import paths


stations_dict = {
    'WBG': {
        'station_name': 'Water backgroung',
        'station_mapping': None,
        'sampler_id': None,
        'latitude': 0.0,
        'longitude': 0.0,
        'altitude': 0.0
    },
    'HEL': {
        'station_name': 'Helsinki',
        'station_mapping': '01HELSINKI',
        'sampler_id': 'Z01',
        'latitude': 60.1699,
        'longitude': 24.9384,
        'altitude': 17.0
    },
    'UTO': {
        'station_name': 'Utö',
        'station_mapping': '09UTÖ',
        'sampler_ID': 'Z09',
        'latitude': 59.7763,
        'longitude': 21.4231,
        'altitude': 9.0
    },
    'KUO': {
        'station_name': 'Kuopio',
        'station_mapping': '77KUOPIO',
        'sampler_id': 'Z77',
        'latitude': 62.8926,
        'longitude': 27.6770,
        'altitude': 75.0
    },
    'PAL': {
        'station_name': 'Pallas',
        'station_mapping': '36PALLAS',
        'sampler_id': 'Z36',
        'latitude': 67.9674,
        'longitude': 24.1196,
        'altitude': 560.0
    }
}


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

        # self.metadata_string = self.findChild(QtWidgets.QPlainTextEdit, 'plainTextMetadata')
        # self.metadata_string.textChanged.connect(self.parse_string)

        self.button_search = self.findChild(QtWidgets.QToolButton, 'searchByLabel')
        self.button_search.clicked.connect(self.search_experiment_metadata_A)

    def search_experiment_metadata(self, label, text_label, text_sampler_id, text_air_volume, text_start_time,
                                   text_end_time, text_temp, text_press, text_description, text_vol_wash,
                                   text_dil_factor, text_filter_fraction):

        station = stations_dict[label[0:3]]

        date = datetime.strptime(label[3:], "%Y%m%d")
        directory_path = paths.external_data_path / 'sampler_raw_data' / station['station_mapping']
        date_str = date.strftime("%d.%m.%y")
        values = None

        for root, dirs, files in os.walk(directory_path):
            for file_name in files:
                if file_name == "SUM.CSV":
                    sum_path = os.path.join(root, file_name)
                    with open(sum_path, "r") as file:
                        lines = file.readlines()
                        for line in lines[1:]:
                            fields = line.strip().split(";")
                            if len(fields) > 2 and fields[2].strip() == date_str.strip():
                                values = line.strip().split(";")
                                break

        if values is not None:
            logging.info(f"Raw data found!\nUsing file: {sum_path}")
            start_datetime = datetime.strptime(values[2] + ' ' + values[3], "%d.%m.%y %H:%M")
            end_datetime = datetime.strptime(values[4] + ' ' + values[5], "%d.%m.%y %H:%M")
            metadata = ExperimentMetadata(
                station=label[0:3],
                experiment_type="filter",
                label=label,
                sampler_id=f"{station['sampler_id']}",
                sampler_status=values[1],
                start_time=start_datetime.strftime("%Y-%m-%d %H:%M"),
                end_time=end_datetime.strftime("%Y-%m-%d %H:%M"),
                filter_position=int(values[7]),
                air_volume=float(values[8]),
                flow=float(values[9]),
                temp=float(values[10]),
                press=float(values[11]),
                v_drop=5e-05,
                v_wash=0.01,
                dil_factor=1,
                filter_fraction=1
            )
            text_label.setPlainText(metadata.label)
            text_sampler_id.setPlainText(metadata.sampler_ID)
            text_air_volume.setPlainText(str(metadata.air_volume))
            text_start_time.setPlainText(metadata.start_time)
            text_end_time.setPlainText(metadata.end_time)
            text_temp.setPlainText(str(metadata.temp))
            text_press.setPlainText(str(metadata.press))
            text_description.setPlainText(metadata.exp_description)
            text_vol_wash.setPlainText(str(metadata.v_wash))
            text_dil_factor.setPlainText(str(metadata.dil_factor))
            text_filter_fraction.setPlainText(str(metadata.filter_fraction))
            return metadata
        else:
            return None

    def search_experiment_metadata_A(self):
        label = self.textLabel.toPlainText().upper()
        metadata = self.search_experiment_metadata(label, self.textLabel, self.textSamplerID, self.textAirVolume,
                                                   self.textStartTime, self.textEndTime, self.textTemp,
                                                   self.textPress, self.textDescription, self.textVolWash,
                                                   self.textDilFactor, self.textFilterFraction)
        self.metadataA = metadata

    # def search_experiment_metadata(self):
    #     label = self.textLabel.toPlainText()
    #
    #     station = stations_dict[label[0:3]]
    #
    #     date = datetime.strptime(label[3:], "%Y%m%d")
    #
    #     metadata_str = find_data_line(paths.external_data_path / 'sampler_raw_data' / station['station_mapping'], date)
    #
    #     if metadata_str is not None:
    #         values = metadata_str.split(";")
    #         start_time = datetime.strptime(f"{values[2]} {values[3]}", "%d.%m.%y %H:%M")
    #         end_time = datetime.strptime(f"{values[4]} {values[5]}", "%d.%m.%y %H:%M")
    #
    #         metadata = {
    #             "station": label[0:3],
    #             "storage_temperature": -20,
    #             "experiment_type": "Filter",
    #             "label": f"{label}",
    #             "sampler_ID": "",
    #             "air_volume": float(values[8]),
    #             "start_time": datetime.strftime(start_time, "%Y-%m-%d %H:%M"),
    #             "end_time": datetime.strftime(end_time, "%Y-%m-%d %H:%M"),
    #             "filter_port": f"{values[7]}",
    #             "sampler_status": f"{values[1]}",
    #             "temp": f"{values[10]}",
    #             "press": f"{values[11]}",
    #             "exp_description": f"",
    #             "run": 0,
    #             "v_drop": 5e-05,
    #             "v_wash": 0.01,
    #             "dil_factor": 1,
    #             "filter_fraction": 1
    #         }
    #
    #         self.textLabel.setPlainText(metadata["label"])
    #         self.textSamplerID.setPlainText(metadata["sampler_ID"])
    #         self.textAirVolume.setPlainText(str(metadata["air_volume"]))
    #         self.textStartTime.setPlainText(metadata["start_time"])
    #         self.textEndTime.setPlainText(metadata["end_time"])
    #         self.textTemp.setPlainText(metadata["temp"])
    #         self.textPress.setPlainText(metadata["press"])
    #         self.textDescription.setPlainText(metadata["exp_description"])
    #         self.textVolWash.setPlainText(str(metadata["v_wash"]))
    #         self.textDilFactor.setPlainText(str(metadata["dil_factor"]))
    #         self.textFilterFraction.setPlainText(str(metadata["filter_fraction"]))
    #
    #         return metadata
    #
    #     else:
    #         return None

    def start_experiment(self):
        if self.metadataA is not None:
            self.metadataA.check_required_fields()

            date_str = time.strftime('%Y%m%d%H%M', time.localtime())

            exp_A_name = paths.raw_data_path / f"{date_str}_{self.metadataA.label}"
            experiment_A = FrESHExperiment(exp_A_name)
            experiment_A.set_metadata(self.metadataA)

            self.hide()

            self.ExperimentUi = ExperimentUi(experiment_A)
            self.ExperimentUi.show()
        else:
            logging.error("Metadata A or B is missing.")

