import PyQt5
from PyQt5 import QtGui, QtWidgets, uic, QtCore
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import QTimer, pyqtSlot, Qt
from PyQt5.QtWidgets import *

from experiment_gui import ExperimentUi
import sys
import time

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
