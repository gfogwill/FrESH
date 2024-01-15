#!/usr/bin/env python3
import sys
import logging

from PyQt5 import QtGui, QtWidgets, uic
from experiment_metadata import ExperimentMetadataUi
from analysis import ExperimentAnalysisUi

from src import paths

# Single experiment .ui file path
SINGLE_EXPERIMENT_UI_FILE = paths.src_module_dir / 'gui' / 'experiment_metadata.ui'

# Double experiment .ui file path
DOUBLE_EXPERIMENT_UI_FILE = paths.src_module_dir / 'gui' / 'double_experiment_metadata.ui'

MAIN_UI_FILE = paths.src_module_dir / 'gui' / 'main.ui'


class MainUi(QtWidgets.QMainWindow):
    def __init__(self, *args, **kwargs):
        super(MainUi, self).__init__(*args, **kwargs)

        uic.loadUi(MAIN_UI_FILE, self)

        self.button_new_single_experiment = self.findChild(QtWidgets.QPushButton, 'newSingleExperimentButton')
        self.button_new_single_experiment.clicked.connect(self.start_single_experiment)

        self.button_new_double_experiment = self.findChild(QtWidgets.QPushButton, 'newDoubleExperimentButton')
        self.button_new_double_experiment.clicked.connect(self.start_double_experiment)

        self.button_view_experiment = self.findChild(QtWidgets.QPushButton, 'viewExperimentButton')
        self.button_view_experiment.clicked.connect(self.view_experiment)

    def start_single_experiment(self):
        self.hide()

        self.ExperimentMetadataUi = ExperimentMetadataUi(SINGLE_EXPERIMENT_UI_FILE)
        self.ExperimentMetadataUi.show()

    def start_double_experiment(self):
        self.hide()

        self.ExperimentMetadataUi = ExperimentMetadataUi(DOUBLE_EXPERIMENT_UI_FILE)
        self.ExperimentMetadataUi.show()


    def view_experiment(self):
        self.hide()

        self.ExperimentAnalysisUi = ExperimentAnalysisUi()
        self.ExperimentAnalysisUi.show()


def main():
    app = QtWidgets.QApplication(sys.argv)
    window = MainUi()
    window.show()
    sys.exit(app.exec_())

logger = logging.getLogger('dual_logger')
logger.setLevel(logging.DEBUG)
if __name__ == '__main__':

    log_fmt = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logging.basicConfig(level=logging.INFO, format=log_fmt)
    main()
