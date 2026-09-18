"""The scan window's per-cycle bookkeeping (src/gui/experiment_gui.py)."""

import json
import logging

import pytest

from src.experiment.metadata import ExperimentMetadata
from src.gui.experiment_gui import ExperimentUi, format_duration


@pytest.fixture
def window(qapp, raw_data_dir):
    templates = [ExperimentMetadata(label='PAL20240619', experiment_type='Filter'),
                 ExperimentMetadata(label='HEL20240619', experiment_type='Filter')]
    ui = ExperimentUi(templates)
    yield ui
    ui.shutdown()


def file_handlers():
    return [h for h in logging.getLogger().handlers if isinstance(h, logging.FileHandler)]


# -- folders ----------------------------------------------------------------

def test_no_folders_are_created_until_something_is_recorded(window, raw_data_dir):
    """Opening the window and closing it should leave nothing behind."""
    assert list(raw_data_dir.iterdir()) == []
    assert window.exp_list == []


def test_a_manual_scan_uses_one_folder_without_a_cycle_suffix(window, raw_data_dir):
    window._open_cycle(None)

    names = sorted(p.name for p in raw_data_dir.iterdir())
    assert names == [f'{window.series_id}_HEL20240619',
                     f'{window.series_id}_PAL20240619']


def test_each_cycle_gets_its_own_folder(window, raw_data_dir):
    for cycle in (1, 2, 12):
        window._open_cycle(cycle)

    names = sorted(p.name for p in raw_data_dir.iterdir())
    assert names == [f'{window.series_id}_HEL20240619_c001',
                     f'{window.series_id}_HEL20240619_c002',
                     f'{window.series_id}_HEL20240619_c012',
                     f'{window.series_id}_PAL20240619_c001',
                     f'{window.series_id}_PAL20240619_c002',
                     f'{window.series_id}_PAL20240619_c012']


def test_every_cycle_records_which_cycle_it_is(window, raw_data_dir):
    window._open_cycle(7)

    for experiment in window.exp_list:
        stored = json.loads((experiment.experiment_path / 'metadata.json').read_text())
        assert stored['cycle_number'] == 7
        assert stored['series_id'] == window.series_id


def test_the_metadata_templates_are_not_mutated(window):
    """Each cycle gets a copy; the templates must stay reusable."""
    window._open_cycle(3)

    assert [m.cycle_number for m in window.metadata_list] == [None, None]


def test_each_cycle_starts_a_sensors_file_with_the_right_header(window):
    window._open_cycle(1)

    for experiment in window.exp_list:
        assert experiment.sensors_file.read_text() == 'datetime,SP,BT,RTD0,RTD1\n'


# -- logging ----------------------------------------------------------------

def test_cycle_log_handlers_do_not_pile_up(window):
    """A 50-cycle series must not leave 100 open files on the root logger."""
    before = len(file_handlers())

    for cycle in range(1, 21):
        window._open_cycle(cycle)

    assert len(file_handlers()) == before + len(window.metadata_list)


def test_shutdown_removes_the_cycle_handlers(window):
    before = len(file_handlers())
    window._open_cycle(1)
    assert len(file_handlers()) > before

    window.shutdown()

    assert len(file_handlers()) == before


# -- the form ---------------------------------------------------------------

def test_the_series_settings_come_from_the_form(window):
    window.maxTemp.setText('0')
    window.minTemp.setText('-45')
    window.freezeTemp.setText('-35')
    window.thawTemp.setText('12')
    window.holdColdMinutes.setText('8')
    window.holdWarmMinutes.setText('6')
    window.coolingRate.setText('1')
    window.heatingRate.setText('5')
    window.cyclesSpinBox.setValue(49)

    settings = window._series_settings()
    settings.validate()

    assert (settings.scan_start_temp, settings.min_temp, settings.freeze_temp,
            settings.thaw_temp) == (0.0, -45.0, -35.0, 12.0)
    assert (settings.hold_cold_minutes, settings.hold_warm_minutes) == (8.0, 6.0)
    assert settings.cycles == 49
    assert settings.folder_per_cycle and settings.wait_for_bath


def test_the_manual_ramp_settings_have_no_holds_and_no_folders(window):
    settings = window._ramp_settings()

    assert settings.hold_cold_minutes == 0.0
    assert settings.hold_warm_minutes == 0.0
    assert settings.cycles is None
    assert not settings.folder_per_cycle
    assert not settings.wait_for_bath


def test_a_bad_number_in_the_form_is_reported_not_raised(window):
    window.freezeTemp.setText('muy frio')

    with pytest.raises(ValueError, match='Hold until'):
        window._series_settings()


def test_the_estimate_line_warns_instead_of_showing_a_duration(window):
    window.minTemp.setText('10')  # above the scan start temp: impossible

    window._update_series_estimate()

    assert window.seriesEstimateLabel.text().startswith('⚠')


def test_the_estimate_line_shows_the_total(window):
    window.maxTemp.setText('0')
    window.minTemp.setText('-45')
    window.freezeTemp.setText('-45')
    window.thawTemp.setText('10')
    window.coolingRate.setText('1')
    window.heatingRate.setText('5')
    window.holdColdMinutes.setText('10')
    window.holdWarmMinutes.setText('10')
    window.cyclesSpinBox.setValue(50)

    window._update_series_estimate()

    assert '65 h' in window.seriesEstimateLabel.text()


# -- which sensor the hold watches ------------------------------------------

@pytest.mark.parametrize('choice, expected', [
    ('Bath (BT)', -30.0),
    ('Probe (RTD0)', -28.0),
])
def test_the_hold_watches_the_selected_sensor(window, choice, expected):
    window.holdSourceComboBox.setCurrentText(choice)

    assert window.hold_temperature({'BT': -30.0, 'RTD0': -28.0}) == expected


# -- odds and ends ----------------------------------------------------------

@pytest.mark.parametrize('seconds, text', [
    (0, '0 min'), (90, '2 min'), (3600, '1 h 00 min'),
    (234000, '65 h 00 min'), (None, 'unbounded'),
])
def test_durations_read_like_a_person_wrote_them(seconds, text):
    assert format_duration(seconds) == text


def test_a_finished_series_lets_go_of_the_last_cycle(window):
    """Otherwise switching Save on afterwards appends to cycle N's folder."""
    window._open_cycle(3)
    assert window.exp_list

    window._finish_series()

    assert window.exp_list == []
    assert window.current_cycle is None


# -- the watchdog reaches the series ----------------------------------------

def test_a_dead_chiller_aborts_the_running_series(window, raw_data_dir):
    """The whole chain: no reading -> watchdog -> abort -> safe setpoint."""
    from src.experiment.series import SAFE_TEMPERATURE, SeriesSettings

    window.series = None
    settings = SeriesSettings(scan_start_temp=0.0, min_temp=-30.0, freeze_temp=-30.0,
                              thaw_temp=10.0, cycles=2, max_missed_readings=3)
    written = []
    window.set_temp = written.append          # no chiller attached here
    window._start_controller(settings)

    for _ in range(3):
        window.read_sensors_data(None)

    assert window.series is None, "the series was not torn down"
    assert written[-1] == SAFE_TEMPERATURE
    # The label keeps saying so, rather than resetting to Idle: whoever walks
    # in the next morning needs to see that it stopped and where.
    assert 'ABORTED' in window.seriesStatusLabel.text()
    assert 'ABORTED' in window.statusBar().currentMessage()
    assert window.startSeriesButton.isEnabled()
    assert not window.abortSeriesButton.isEnabled()


def test_a_good_reading_keeps_the_series_running(window, raw_data_dir):
    from src.experiment.series import SeriesSettings

    settings = SeriesSettings(scan_start_temp=0.0, min_temp=-30.0, freeze_temp=-30.0,
                              thaw_temp=10.0, cycles=2, max_missed_readings=3)
    window.set_temp = lambda t: None
    window._start_controller(settings)

    for _ in range(10):
        window.read_sensors_data({'BT': -5.0, 'SP': -5.0, 'RTD0': -4.6, 'RTD1': -4.5})

    assert window.series is not None
