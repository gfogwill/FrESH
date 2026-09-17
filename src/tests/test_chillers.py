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
