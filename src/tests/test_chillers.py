"""Chiller drivers and the per-machine configuration."""

import pytest

from src.daq.chillers import (CHILLERS, LAUDARE1050, LAUDARP1845, LaudaSerial,
                              make_chiller)


def config(model):
    return {'CHILLER': {'MODEL': model}, 'SERIAL': {}}


@pytest.mark.parametrize('model, expected', [
    ('RE1050', LAUDARE1050),
    ('RP1845', LAUDARP1845),
    ('re1050', LAUDARE1050),   # the config file is not case sensitive
])
def test_make_chiller_picks_the_driver(model, expected):
    assert isinstance(make_chiller(config(model)), expected)


def test_unknown_model_says_what_is_supported():
    with pytest.raises(ValueError, match='RE1050'):
        make_chiller(config('LAUDA-9000'))


def test_every_driver_is_registered_under_its_own_model_name():
    for model, chiller_class in CHILLERS.items():
        assert chiller_class.MODEL == model


class FakeSerial:
    """Records what is written and replies with canned lines."""

    def __init__(self, replies=()):
        self.written = []
        self.replies = list(replies)

    def write(self, data):
        self.written.append(data)

    def readline(self):
        return self.replies.pop(0) if self.replies else b''

    def close(self):
        pass


def test_setpoint_command_is_unchanged():
    chiller = LaudaSerial()
    chiller.ser = FakeSerial([b'OK\r\n'])
    chiller.connected = True

    assert chiller.set_temperature(-12.5) is True
    assert chiller.ser.written == [b'OUT_SP_00_-12.5\r']


def test_an_unacknowledged_setpoint_is_reported(caplog):
    chiller = LaudaSerial()
    chiller.ser = FakeSerial([b'ERR\r\n'])
    chiller.connected = True

    assert chiller.set_temperature(-12.5) is False
    assert 'did not acknowledge' in caplog.text


def test_nothing_is_written_while_disconnected():
    chiller = LaudaSerial()
    chiller.ser = FakeSerial()

    assert chiller.set_temperature(-5) is False
    assert chiller.ser.written == []


def test_a_bad_reading_does_not_raise():
    chiller = LaudaSerial()
    chiller.ser = FakeSerial([b'not a number'] * 7)
    chiller.connected = True

    assert chiller.read_all_temp() == (None,) * 7
    assert chiller.get_data() is None


def test_a_failed_read_is_reported_to_the_gui(qapp):
    """Regression: the series watchdog can only count what it hears about.

    read_temps used to emit nothing when the chiller stopped answering, so a
    running series never learned it had lost the hardware.
    """
    from PyQt6.QtCore import QObject

    from src.gui.threads import DataWorker

    worker = DataWorker.__new__(DataWorker)   # no chiller, no thread started
    QObject.__init__(worker)
    worker.threadactive = True
    worker.connected = True
    worker.chiller = type('DeadChiller', (), {'get_data': lambda self: None})()

    received = []
    worker.read_data_signal.connect(received.append)
    worker.read_temps()

    assert received == [None]

# -- which serial port the chiller is on ------------------------------------

class FakePort:
    def __init__(self, device, description='', hwid=''):
        self.device, self.description, self.hwid = device, description, hwid


@pytest.fixture
def ports(monkeypatch):
    """Control what the machine appears to have plugged in."""
    import serial.tools.list_ports

    found = []
    monkeypatch.setattr(serial.tools.list_ports, 'comports', lambda: found)
    return found


def test_a_single_usb_port_is_found_automatically(ports):
    from src.daq.chillers import find_chiller_port

    ports.append(FakePort('/dev/ttyUSB0', 'FT232R USB UART', 'USB VID:PID=0403:6001'))

    assert find_chiller_port(config(None)) == '/dev/ttyUSB0'


def test_the_adam_port_is_never_picked_for_the_chiller(ports):
    """Regression: the RE1050 has two USB serial devices.

    Opening the ADAM's port as the chiller's succeeds on Linux and leaves both
    talking over one line, which shows up as "no reply from the chiller"
    while the ADAM readings keep working.
    """
    from src.daq.chillers import find_chiller_port

    ports.append(FakePort('/dev/ttyUSB1', 'USB-RS485 adapter', 'USB VID:PID=0403:6001'))
    ports.append(FakePort('/dev/ttyUSB0', 'FT232R USB UART', 'USB VID:PID=0403:6001'))

    assert find_chiller_port(config(None), exclude=('/dev/ttyUSB1',)) == '/dev/ttyUSB0'


def test_the_configured_port_wins_over_any_guess(ports):
    from src.daq.chillers import find_chiller_port

    ports.append(FakePort('/dev/ttyUSB0', 'FT232R USB UART', 'USB'))
    settings = {'CHILLER': {'MODEL': 'RE1050', 'PORT': '/dev/ttyS3'}, 'SERIAL': {}}

    assert find_chiller_port(settings) == '/dev/ttyS3'


def test_the_description_is_preferred_over_the_hwid(ports):
    """The original matched on the description only; hwid is the fallback.

    Widening it to 'description OR hwid' changed which port got picked on a
    machine with more than one, which is what broke the RE1050.
    """
    from src.daq.chillers import find_chiller_port

    ports.append(FakePort('/dev/ttyS0', 'serial controller', 'USB VID:PID=1234'))
    ports.append(FakePort('/dev/ttyUSB0', 'FT232R USB UART', 'USB VID:PID=0403'))

    assert find_chiller_port(config(None)) == '/dev/ttyUSB0'


def test_the_hwid_is_still_used_when_no_description_matches(ports):
    from src.daq.chillers import find_chiller_port

    ports.append(FakePort('/dev/ttyS0', 'serial controller', 'USB VID:PID=1234'))

    assert find_chiller_port(config(None)) == '/dev/ttyS0'


def test_no_port_left_is_reported_not_guessed(ports, caplog):
    from src.daq.chillers import find_chiller_port

    ports.append(FakePort('/dev/ttyUSB1', 'USB-RS485 adapter', 'USB'))

    assert find_chiller_port(config(None), exclude=('/dev/ttyUSB1',)) is None
    assert 'Set [CHILLER] PORT' in caplog.text


def test_the_re1050_reserves_the_adam_port():
    from src.daq.chillers import LAUDARE1050

    chiller = LAUDARE1050({'CHILLER': {'MODEL': 'RE1050'},
                           'SERIAL': {'PORT': '/dev/ttyUSB1'}})

    assert chiller.reserved_ports() == ('/dev/ttyUSB1',)


def test_a_chiller_without_an_adam_reserves_nothing():
    from src.daq.chillers import LAUDARP1845

    assert LAUDARP1845(config('RP1845')).reserved_ports() == ()


# -- diagnosing a bad port --------------------------------------------------

def test_a_silent_chiller_says_which_readings_are_missing(caplog):
    """The message used to be 'One or more temperature readings returned None'."""
    chiller = LaudaSerial()
    chiller.ser = FakeSerial([b''] * 7)
    chiller.connected = True
    chiller.port = '/dev/ttyUSB1'

    chiller.read_all_temp()

    assert 'bath temperature' in caplog.text
    assert 'setpoint' in caplog.text
    assert '/dev/ttyUSB1' in caplog.text
