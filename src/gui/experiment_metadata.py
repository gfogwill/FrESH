import logging

import PyQt5
from PyQt5 import QtGui, QtWidgets, uic, QtCore
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import QTimer, pyqtSlot, Qt
from PyQt5.QtWidgets import *

import os
import sys
import time
from datetime import datetime

from src.gui.experiment_gui import ExperimentUi
from src.experiment.experiment import FrESHExperiment, ExperimentMetadata
from src import paths
from src.daq.IniLoader import IniLoader


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
        'sampler_id': 'Z09',
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


class ExperimentMetadataUi(QtWidgets.QMainWindow):
    def __init__(self, ui_file, *args, **kwargs):
        super(ExperimentMetadataUi, self).__init__(*args, **kwargs)

        uic.loadUi(ui_file, self)

        self.metadata_experiments = []

        self.experiment_type_comboboxA = self.findChild(QtWidgets.QComboBox, 'comboBoxSampleType_A')
        self.experiment_type_comboboxA.currentTextChanged.connect(lambda: self.update_experiment_type('A'))

        self.experiment_type_comboboxB = self.findChild(QtWidgets.QComboBox, 'comboBoxSampleType_B')
        self.experiment_type_comboboxB.currentTextChanged.connect(lambda: self.update_experiment_type('B'))

        # Connect the button signals to their respective slots
        self.button_confirm = self.findChild(QtWidgets.QDialogButtonBox, 'ConfirmbuttonBox')
        self.button_confirm.accepted.connect(self.start_experiment)

        self.button_search_A = self.findChild(QtWidgets.QToolButton, 'searchByLabel_A')
        self.button_search_A.clicked.connect(lambda: self.search_experiment_metadata('A'))

        try:
            self.button_search_B = self.findChild(QtWidgets.QToolButton, 'searchByLabel_B')
            self.button_search_B.clicked.connect(lambda: self.search_experiment_metadata('B'))
        except AttributeError:
            self.button_search_B = None

    def update_experiment_type(self, experiment_key):
        experiment_type = self.findChild(QtWidgets.QComboBox, f'comboBoxSampleType_{experiment_key}').currentText()

        if experiment_type == 'Filter':
            self.findChild(QtWidgets.QPlainTextEdit, f'textSamplerID_{experiment_key}').setEnabled(True)
            self.findChild(QtWidgets.QPlainTextEdit, f'textAirVolume_{experiment_key}').setEnabled(True)
            self.findChild(QtWidgets.QPlainTextEdit, f'textStartTime_{experiment_key}').setEnabled(True)
            self.findChild(QtWidgets.QPlainTextEdit, f'textEndTime_{experiment_key}').setEnabled(True)
            self.findChild(QtWidgets.QPlainTextEdit, f'textTemp_{experiment_key}').setEnabled(True)
            self.findChild(QtWidgets.QPlainTextEdit, f'textPress_{experiment_key}').setEnabled(True)
            self.findChild(QtWidgets.QPlainTextEdit, f'textDilFactor_{experiment_key}').setEnabled(True)
            self.findChild(QtWidgets.QPlainTextEdit, f'textFilterFraction_{experiment_key}').setEnabled(True)
        elif experiment_type == 'Field background':
            self.findChild(QtWidgets.QPlainTextEdit, f'textSamplerID_{experiment_key}').setEnabled(True)
            self.findChild(QtWidgets.QPlainTextEdit, f'textAirVolume_{experiment_key}').setEnabled(False)
            self.findChild(QtWidgets.QPlainTextEdit, f'textStartTime_{experiment_key}').setEnabled(True)
            self.findChild(QtWidgets.QPlainTextEdit, f'textEndTime_{experiment_key}').setEnabled(True)
            self.findChild(QtWidgets.QPlainTextEdit, f'textTemp_{experiment_key}').setEnabled(False)
            self.findChild(QtWidgets.QPlainTextEdit, f'textPress_{experiment_key}').setEnabled(False)
            self.findChild(QtWidgets.QPlainTextEdit, f'textDilFactor_{experiment_key}').setEnabled(True)
            self.findChild(QtWidgets.QPlainTextEdit, f'textFilterFraction_{experiment_key}').setEnabled(True)
        elif experiment_type == 'Water background':
            self.findChild(QtWidgets.QPlainTextEdit, f'textSamplerID_{experiment_key}').setEnabled(False)
            self.findChild(QtWidgets.QPlainTextEdit, f'textAirVolume_{experiment_key}').setEnabled(False)
            self.findChild(QtWidgets.QPlainTextEdit, f'textStartTime_{experiment_key}').setEnabled(False)
            self.findChild(QtWidgets.QPlainTextEdit, f'textEndTime_{experiment_key}').setEnabled(False)
            self.findChild(QtWidgets.QPlainTextEdit, f'textTemp_{experiment_key}').setEnabled(False)
            self.findChild(QtWidgets.QPlainTextEdit, f'textPress_{experiment_key}').setEnabled(False)
            self.findChild(QtWidgets.QPlainTextEdit, f'textDilFactor_{experiment_key}').setEnabled(False)
            self.findChild(QtWidgets.QPlainTextEdit, f'textFilterFraction_{experiment_key}').setEnabled(False)

    def search_experiment_metadata(self, experiment_key):
        text_label = self.findChild(QtWidgets.QPlainTextEdit, f'textLabel_{experiment_key}')
        text_sampler_id = self.findChild(QtWidgets.QPlainTextEdit, f'textSamplerID_{experiment_key}')
        text_air_volume = self.findChild(QtWidgets.QPlainTextEdit, f'textAirVolume_{experiment_key}')
        text_start_time = self.findChild(QtWidgets.QPlainTextEdit, f'textStartTime_{experiment_key}')
        text_end_time = self.findChild(QtWidgets.QPlainTextEdit, f'textEndTime_{experiment_key}')
        text_temp = self.findChild(QtWidgets.QPlainTextEdit, f'textTemp_{experiment_key}')
        text_press = self.findChild(QtWidgets.QPlainTextEdit, f'textPress_{experiment_key}')
        text_description = self.findChild(QtWidgets.QPlainTextEdit, f'textDescription_{experiment_key}')
        text_vol_wash = self.findChild(QtWidgets.QPlainTextEdit, f'textVolWash_{experiment_key}')
        text_dil_factor = self.findChild(QtWidgets.QPlainTextEdit, f'textDilFactor_{experiment_key}')
        text_filter_fraction = self.findChild(QtWidgets.QPlainTextEdit, f'textFilterFraction_{experiment_key}')

        label = text_label.toPlainText().upper()
        metadata = self._retrieve_metadata(label)
        if metadata is not None:
            self._populate_metadata_fields(metadata, text_label, text_sampler_id, text_air_volume, text_start_time,
                                           text_end_time, text_temp, text_press, text_description, text_vol_wash,
                                           text_dil_factor, text_filter_fraction)

    def _retrieve_metadata(self, label):
        station = stations_dict.get(label[0:3])
        if not station:
            logging.error(f"Station not found for label: {label}")
            return None

        try:
            date = datetime.strptime(label[3:], "%Y%m%d")
            directory_path = paths.external_data_path / 'sampler_raw_data' / station['station_mapping']
            date_str = date.strftime("%d.%m.%y")
        except ValueError:
            return None

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
                                return self._create_experiment_metadata(values, label, "filter")

        logging.warning(f"No raw data found for label: {label}")

        return None

    def _create_experiment_metadata(self, values, label, experiment_type):
        start_datetime = datetime.strptime(values[2] + ' ' + values[3], "%d.%m.%y %H:%M")
        end_datetime = datetime.strptime(values[4] + ' ' + values[5], "%d.%m.%y %H:%M")
        return ExperimentMetadata(
            station=label[0:3],
            experiment_type=experiment_type,
            label=label,
            sampler_id=f"{stations_dict[label[0:3]]['sampler_id']}",
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

    def _populate_metadata_fields(self, metadata, text_label, text_sampler_id, text_air_volume, text_start_time,
                                  text_end_time, text_temp, text_press, text_description, text_vol_wash,
                                  text_dil_factor, text_filter_fraction):
        text_label.setPlainText(metadata.label)
        text_sampler_id.setPlainText(metadata.sampler_id)
        text_air_volume.setPlainText(str(metadata.air_volume))
        text_start_time.setPlainText(metadata.start_time)
        text_end_time.setPlainText(metadata.end_time)
        text_temp.setPlainText(str(metadata.temp))
        text_press.setPlainText(str(metadata.press))
        text_description.setPlainText(metadata.exp_description)
        text_vol_wash.setPlainText(str(metadata.v_wash))
        text_dil_factor.setPlainText(str(metadata.dil_factor))
        text_filter_fraction.setPlainText(str(metadata.filter_fraction))

    def _get_metadata_from_form(self, experiment_key):
        experiment_type = self.findChild(QtWidgets.QComboBox, f'comboBoxSampleType_{experiment_key}').currentText()

        text_label = self.findChild(QtWidgets.QPlainTextEdit, f'textLabel_{experiment_key}')
        text_sampler_id = self.findChild(QtWidgets.QPlainTextEdit, f'textSamplerID_{experiment_key}')
        text_air_volume = self.findChild(QtWidgets.QPlainTextEdit, f'textAirVolume_{experiment_key}')
        text_start_time = self.findChild(QtWidgets.QPlainTextEdit, f'textStartTime_{experiment_key}')
        text_end_time = self.findChild(QtWidgets.QPlainTextEdit, f'textEndTime_{experiment_key}')
        text_temp = self.findChild(QtWidgets.QPlainTextEdit, f'textTemp_{experiment_key}')
        text_press = self.findChild(QtWidgets.QPlainTextEdit, f'textPress_{experiment_key}')
        text_description = self.findChild(QtWidgets.QPlainTextEdit, f'textDescription_{experiment_key}')
        text_vol_wash = self.findChild(QtWidgets.QPlainTextEdit, f'textVolWash_{experiment_key}')
        text_dil_factor = self.findChild(QtWidgets.QPlainTextEdit, f'textDilFactor_{experiment_key}')
        text_filter_fraction = self.findChild(QtWidgets.QPlainTextEdit, f'textFilterFraction_{experiment_key}')

        label = text_label.toPlainText().upper()
        sampler_id = text_sampler_id.toPlainText()
        air_volume = float(text_air_volume.toPlainText()) if text_air_volume.toPlainText() else None
        start_time = text_start_time.toPlainText()
        end_time = text_end_time.toPlainText()
        temp = float(text_temp.toPlainText()) if text_temp.toPlainText() else None
        press = float(text_press.toPlainText()) if text_press.toPlainText() else None
        description = text_description.toPlainText()
        vol_wash = float(text_vol_wash.toPlainText()) if text_vol_wash.toPlainText() else None
        dil_factor = float(text_dil_factor.toPlainText()) if text_dil_factor.toPlainText() else None
        filter_fraction = float(text_filter_fraction.toPlainText()) if text_filter_fraction.toPlainText() else None

        ini = IniLoader.load('perezfo', paths.etc_path / 'test.ini')

        return ExperimentMetadata(
            station=label[0:3],
            experiment_type=experiment_type,
            label=label,
            sampler_id=sampler_id,
            start_time=start_time,
            end_time=end_time,
            air_volume=air_volume,
            temp=temp,
            press=press,
            exp_description=description,
            v_wash=vol_wash,
            dil_factor=dil_factor,
            filter_fraction=filter_fraction,
            v_drop=5e-05,
            chiller_model=ini['CHILLER']['MODEL']
        )

    def _update_metadata_list(self):
        self.metadata_experiments.clear()

        # Check for experiment A
        label_A = self.findChild(QtWidgets.QPlainTextEdit, 'textLabel_A').toPlainText()
        if label_A:
            metadata_A = self._retrieve_metadata(label_A.upper())
            if metadata_A is not None:
                self.metadata_experiments.append(metadata_A)
            else:
                metadata_A = self._get_metadata_from_form('A')
                self.metadata_experiments.append(metadata_A)

        # Check for experiment B if the button_search_B exists
        if self.button_search_B:
            label_B = self.findChild(QtWidgets.QPlainTextEdit, 'textLabel_B').toPlainText()
            if label_B:
                metadata_B = self._retrieve_metadata(label_B.upper())
                if metadata_B is not None:
                    self.metadata_experiments.append(metadata_B)
                else:
                    metadata_B = self._get_metadata_from_form('B')
                    self.metadata_experiments.append(metadata_B)

    def start_experiment(self):
        self._update_metadata_list()

        if len(self.metadata_experiments) > 0:
            for metadata in self.metadata_experiments:
                metadata.check_required_fields()

            if len(self.metadata_experiments) > 1:
                if self.metadata_experiments[0].label == self.metadata_experiments[1].label:
                    logging.warning("Labels are the same!!\n Rename and try again.")
                    return

            date_str = time.strftime('%Y%m%d%H%M', time.localtime())

            exp_list = []
            for i, metadata in enumerate(self.metadata_experiments, 1):
                exp_name = paths.raw_data_path / f"{date_str}_{metadata.label}"
                experiment = FrESHExperiment(exp_name)
                experiment.set_metadata(metadata)
                exp_list.append(experiment)

            self.hide()
            self.ExperimentUi = ExperimentUi(exp_list)
            self.ExperimentUi.show()
        else:
            logging.error("No valid metadata for the experiments.")
