import logging
import os
import sys
import time
from datetime import datetime

import PyQt5
from PyQt5 import QtGui, QtWidgets, uic, QtCore
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import QTimer, pyqtSlot, Qt
from PyQt5.QtWidgets import *

from src.gui.experiment_gui import ExperimentUi
from src.gui.experiment_metadata import ExperimentMetadataUi
from src.experiment.experiment import FrESHExperiment, ExperimentMetadata
from src import paths


def test_experiment_metadata_ui_with_one_experiment():
    app = QtWidgets.QApplication([])
    window = ExperimentMetadataUi()

    # Simulate UI behavior for experiment A
    window.findChild(QtWidgets.QPlainTextEdit, 'textLabel_A').setPlainText('PAL20220909')
    window.button_search_A.clicked.emit()

    # Fill in some values for experiment A
    window.findChild(QtWidgets.QPlainTextEdit, 'textSamplerID_A').setPlainText('Z01')
    window.findChild(QtWidgets.QPlainTextEdit, 'textAirVolume_A').setPlainText('100')
    window.findChild(QtWidgets.QPlainTextEdit, 'textStartTime_A').setPlainText('2023-07-21 08:00')
    window.findChild(QtWidgets.QPlainTextEdit, 'textEndTime_A').setPlainText('2023-07-21 10:00')

    # Confirm and start the experiment
    window.button_confirm.accepted.emit()

    # Validate that the metadata_experiments list contains only one experiment
    assert len(window.metadata_experiments) == 1

    # Validate the experiment metadata in the list
    experiment_A = window.metadata_experiments[0]
    assert experiment_A.label == 'PAL20220909'
    assert experiment_A.sampler_id == 'Z36'
    assert experiment_A.air_volume == 21307.4
    assert experiment_A.start_time == '2022-09-09 08:00'
    assert experiment_A.end_time == '2022-09-10 08:00'


def test_experiment_metadata_ui_with_two_experiments():
    app = QtWidgets.QApplication([])
    window = ExperimentMetadataUi()

    # Simulate UI behavior for experiment A
    window.findChild(QtWidgets.QPlainTextEdit, 'textLabel_A').setPlainText('PAL20220909')
    window.button_search_A.clicked.emit()

    # Fill in some values for experiment A
    window.findChild(QtWidgets.QPlainTextEdit, 'textSamplerID_A').setPlainText('Z01')
    window.findChild(QtWidgets.QPlainTextEdit, 'textAirVolume_A').setPlainText('100')
    window.findChild(QtWidgets.QPlainTextEdit, 'textStartTime_A').setPlainText('2023-07-21 08:00')
    window.findChild(QtWidgets.QPlainTextEdit, 'textEndTime_A').setPlainText('2023-07-21 10:00')

    # Simulate UI behavior for experiment B
    window.findChild(QtWidgets.QPlainTextEdit, 'textLabel_B').setPlainText('HEL20220910')
    window.button_search_B.clicked.emit()

    # Fill in some values for experiment B
    window.findChild(QtWidgets.QPlainTextEdit, 'textSamplerID_B').setPlainText('Z09')
    window.findChild(QtWidgets.QPlainTextEdit, 'textAirVolume_B').setPlainText('200')
    window.findChild(QtWidgets.QPlainTextEdit, 'textStartTime_B').setPlainText('2023-07-21 09:00')
    window.findChild(QtWidgets.QPlainTextEdit, 'textEndTime_B').setPlainText('2023-07-21 11:00')

    # Confirm and start the experiments
    window.button_confirm.accepted.emit()

    # Validate that the metadata_experiments list contains two experiments
    assert len(window.metadata_experiments) == 2

    # Validate the experiment metadata in the list
    experiment_A = window.metadata_experiments[0]
    assert experiment_A.label == 'PAL20220909'
    assert experiment_A.sampler_id == 'Z01'
    assert experiment_A.air_volume == 100.0
    assert experiment_A.start_time == '2023-07-21 08:00'
    assert experiment_A.end_time == '2023-07-21 10:00'

    experiment_B = window.metadata_experiments[1]
    assert experiment_B.label == 'HEL20220910'
    assert experiment_B.sampler_id == 'Z09'
    assert experiment_B.air_volume == 200.0
    assert experiment_B.start_time == '2023-07-21 09:00'
    assert experiment_B.end_time == '2023-07-21 11:00'


if __name__ == "__main__":
    test_experiment_metadata_ui_with_one_experiment()
    test_experiment_metadata_ui_with_two_experiments()
