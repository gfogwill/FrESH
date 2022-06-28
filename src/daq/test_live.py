import sys
import pyqtgraph as pg

from PyQt5.QtWidgets import *
from PyQt5.QtCore import QTimer

from src.daq import io


class Window(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Lauda temperature control")
        self.setGeometry(50, 50, 1200, 660)

        self.timer = None
        self.daq = None
        self.line1 = None
        self.line2 = None

        self.bath_temp = []
        self.setpoint = []

        self.UI()

    def UI(self):
        self.setStyleSheet("background-color:white;font-size:12pt;font-family:Times;")

        mainLayout = QVBoxLayout()
        bottomFormLayout = QFormLayout()
        topLayout = QVBoxLayout()

        mainLayout.addLayout(topLayout, 70)
        mainLayout.addLayout(bottomFormLayout, 30)

        setTempWidget = QHBoxLayout()
        self.temp_set_label = QLabel("Set temperature :")
        self.temp_set = QLineEdit('17')
        self.temp_set_btn = QPushButton("Set", self)
        self.temp_set_btn.clicked.connect(self.set_temp)
        setTempWidget.addWidget(self.temp_set)
        setTempWidget.addWidget(self.temp_set_btn)

        self.accx = QLabel("Setpoint [CH4] :")
        self.accx_value = QLabel("...")
        self.accx.setStyleSheet("color:green;")
        self.accx_value.setStyleSheet("color:green;")

        self.accy = QLabel("Bath temp [CH5] :")
        self.accy_value = QLabel("...")
        self.accy.setStyleSheet("color:red;")
        self.accy_value.setStyleSheet("color:red;")

        self.btn_connect = QPushButton("Connect", self)
        self.btn_connect.clicked.connect(self.connect_system)

        self.btn_exit = QPushButton("Exit", self)
        self.btn_exit.clicked.connect(self.exit)

        self.graphWidget = pg.PlotWidget()

        bottomFormLayout.setContentsMargins(10, 10, 10, 10)
        bottomFormLayout.addRow(self.temp_set_label, setTempWidget)

        bottomFormLayout.addRow(self.btn_connect)
        bottomFormLayout.addRow(self.btn_exit)
        bottomFormLayout.addRow(self.accx, self.accx_value)
        bottomFormLayout.addRow(self.accy, self.accy_value)

        topLayout.addWidget(self.graphWidget)

        self.setLayout(mainLayout)

        self.timer = QTimer()
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.draw)
        
        self.show()

    def set_temp(self):
        t = float(self.temp_set.text())
        print(f'Setting temperature to: {t}')
        self.daq.set_temperature(t)

    def connect_system(self):
        print("Connecting System")
        self.daq = io.Daq()
        self.daq.set_starting_temp(float(self.temp_set.text()))

        self.timer.start()

    def exit(self):
        self.timer.stop()
        self.daq.daq_device.release()
        sys.exit()
       
    def draw(self):
        self.bath_temp.append(self.daq.get_bath_temp(samples=20, interval=1e-3))
        self.setpoint.append(self.daq.get_setpoint_temp(samples=20, interval=1e-3))

        self.accx_value.setText(f'{(self.setpoint[-1] / 100 * 1e3):.3f} mV')
        self.accy_value.setText(f'{(self.bath_temp[-1] / 100 * 1e3):.3f} mV')

        pen = pg.mkPen(color=(255, 0, 0), width=1)
        pen2 = pg.mkPen(color='green', width=1)

        self.graphWidget.setLabel('left', 'Bath temp [ºC]', color='red', size=30)
        self.graphWidget.setLabel('right', 'Setpoint temp [ºC]', color='green', size=30)
        self.graphWidget.setLabel('bottom', 'Time', size=30)

        self.line1 = self.graphWidget.plot(self.bath_temp, name="Bath temp.", pen=pen)
        self.line2 = self.graphWidget.plot(self.setpoint, name="Setpoint temp.", pen=pen2)


def main():
    App = QApplication(sys.argv)
    window = Window()
    sys.exit(App.exec_())


if __name__ == '__main__':
    main()
