import sys
import random
import matplotlib

matplotlib.use('Qt5Agg')

from PyQt5 import QtCore, QtWidgets

from src.daq import io


class MainWindow(QtWidgets.QMainWindow):

    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)

        window = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(QtWidgets.QPushButton('Top'))
        layout.addWidget(QtWidgets.QPushButton('Bottom'))

        self.daq = io.Daq()

        self.bath_temp = []
        self.setpoint = []
        self.update_plot()

        window.setLayout(layout)
        self.show()

        # Setup a timer to trigger the redraw by calling update_plot.
        self.timer = QtCore.QTimer()
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.update_plot)
        self.timer.start()

    def update_plot(self):
        # Drop off the first y element, append a new one.
        self.bath_temp.append(self.daq.get_bath_temp())
        self.canvas.axes.cla()  # Clear the canvas.
        self.canvas.axes.plot(self.bath_temp, 'r')
        # Trigger the canvas to update and redraw.
        self.canvas.draw()


app = QtWidgets.QApplication(sys.argv)
w = MainWindow()
app.exec_()
