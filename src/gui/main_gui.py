#!/usr/bin/env python3
import sys
import logging

from PyQt5 import QtGui, QtWidgets, uic
from experiment_gui import ExperimentUi

from src import paths


class MainUi(QtWidgets.QMainWindow):
    def __init__(self, *args, **kwargs):
        super(MainUi, self).__init__(*args, **kwargs)

        uic.loadUi('main.ui', self)

        self.button_new_experiment = self.findChild(QtWidgets.QPushButton, 'newExperimentButton')  # Find the button
        self.button_new_experiment.clicked.connect(self.start_experiment)

    def start_experiment(self):
        self.hide()
        self.ExperimentUi = ExperimentUi(save_exp=self.saveCheckBox.isChecked(),
                                         exp_description=self.descriptionPlainTextEdit.toPlainText())
        self.ExperimentUi.show()


def main():
    app = QtWidgets.QApplication(sys.argv)
    window = MainUi()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    log_fmt = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logging.basicConfig(level=logging.INFO, format=log_fmt)
    main()
