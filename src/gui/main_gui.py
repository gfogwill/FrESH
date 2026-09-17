#!/usr/bin/env python3
"""Entry point: python -m src.gui.main_gui"""

import logging
import sys

from PyQt6 import QtWidgets, uic

from src import paths
from src.gui.analysis import ExperimentAnalysisUi
from src.gui.experiment_metadata import ExperimentMetadataUi

MAIN_UI_FILE = paths.src_module_dir / 'gui' / 'main.ui'
DOUBLE_EXPERIMENT_UI_FILE = paths.src_module_dir / 'gui' / 'double_experiment_metadata.ui'

LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'


class MainUi(QtWidgets.QMainWindow):
    def __init__(self, *args, **kwargs):
        super(MainUi, self).__init__(*args, **kwargs)

        uic.loadUi(MAIN_UI_FILE, self)

        self.ExperimentMetadataUi = None
        self.ExperimentAnalysisUi = None

        self.button_new_double_experiment = self.findChild(QtWidgets.QPushButton, 'newDoubleExperimentButton')
        self.button_new_double_experiment.clicked.connect(self.start_double_experiment)

        self.button_view_experiment = self.findChild(QtWidgets.QPushButton, 'viewExperimentButton')
        self.button_view_experiment.clicked.connect(self.view_experiment)

    def start_double_experiment(self):
        self.hide()

        self.ExperimentMetadataUi = ExperimentMetadataUi(DOUBLE_EXPERIMENT_UI_FILE)
        self.ExperimentMetadataUi.show()

    def view_experiment(self):
        self.hide()

        self.ExperimentAnalysisUi = ExperimentAnalysisUi()
        self.ExperimentAnalysisUi.show()


def main():
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)

    app = QtWidgets.QApplication(sys.argv)
    window = MainUi()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
