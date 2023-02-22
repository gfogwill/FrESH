#!/usr/bin/env python3
import sys
import logging

from PyQt5 import QtGui, QtWidgets, uic
from experiment_metadata import ExperimentMetadataUi
from analysis import ExperimentAnalysisUi

from src import paths


class MainUi(QtWidgets.QMainWindow):
    def __init__(self, *args, **kwargs):
        super(MainUi, self).__init__(*args, **kwargs)

        uic.loadUi('main.ui', self)

        # Find and connect the button
        self.button_new_experiment = self.findChild(QtWidgets.QPushButton, 'newExperimentButton')
        self.button_new_experiment.clicked.connect(self.start_experiment)

        self.button_view_experiment = self.findChild(QtWidgets.QPushButton, 'viewExperimentButton')
        self.button_view_experiment.clicked.connect(self.view_experiment)

    def start_experiment(self):
        self.hide()

        self.ExperimentMetadataUi = ExperimentMetadataUi()
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


if __name__ == '__main__':
    log_fmt = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logging.basicConfig(level=logging.INFO, format=log_fmt)
    main()
