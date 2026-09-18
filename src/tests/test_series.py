"""The freeze/thaw series state machine (src/experiment/series.py)."""

import pytest

from src.experiment.series import (Phase, SAFE_TEMPERATURE, SeriesController,
                                   SeriesSettings)


class FakeClock:
    """A clock the tests move by hand, so holds do not take real minutes."""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, minutes):
        self.now += minutes * 60


@pytest.fixture
def clock():
    return FakeClock()


def make(clock, **overrides):
    settings = SeriesSettings(**{
        'scan_start_temp': 0.0, 'min_temp': -30.0, 'freeze_temp': -30.0,
        'thaw_temp': 10.0, 'cooling_rate': 60.0, 'heating_rate': 60.0,
        'hold_cold_minutes': 5.0, 'hold_warm_minutes': 5.0, 'cycles': 2,
        **overrides})
    return SeriesController(settings, clock=clock)


class Recorder:
    """Collects everything a controller emits."""

    def __init__(self, controller):
        self.setpoints, self.phases = [], []
        self.started, self.finished, self.done, self.aborted = [], [], [], []
        controller.setpoint_changed.connect(self.setpoints.append)
        controller.phase_changed.connect(lambda p, c: self.phases.append((p, c)))
        controller.cycle_started.connect(self.started.append)
        controller.cycle_finished.connect(self.finished.append)
        controller.series_finished.connect(lambda: self.done.append(True))
        controller.aborted.connect(self.aborted.append)


def run(controller, clock, bath_follows=True, ticks=2000, lag=0.0):
    """Tick the controller, optionally letting the bath track the setpoint."""
    for _ in range(ticks):
        if controller.phase.is_finished:
            break
        if bath_follows:
            controller.update_temperature(controller.setpoint - lag)
        clock.advance(controller.settings.step_interval / 60.0)
        controller.tick()


# -- settings ---------------------------------------------------------------

@pytest.mark.parametrize('overrides, message', [
    (dict(min_temp=5.0), 'below the scan start'),
    (dict(thaw_temp=-40.0), 'above the'),
    (dict(freeze_temp=-50.0), 'cannot be asked to reach'),
    (dict(freeze_temp=5.0), 'below the scan start'),
    (dict(cooling_rate=0.0), 'greater than zero'),
    (dict(cycles=0), 'at least one cycle'),
    (dict(hold_cold_minutes=-1), 'cannot be negative'),
])
def test_impossible_settings_are_rejected(qapp, clock, overrides, message):
    with pytest.raises(ValueError, match=message):
        make(clock, **overrides)


def test_a_higher_freeze_temp_than_the_setpoint_floor_is_allowed(qapp, clock):
    """The chiller may not reach min_temp; waiting for a warmer bath is fine."""
    make(clock, min_temp=-45.0, freeze_temp=-35.0)


def test_rates_are_degrees_per_minute(qapp, clock):
    controller = make(clock, cooling_rate=1.0, heating_rate=5.0)

    assert controller.settings.cooling_step == pytest.approx(1.0 * 6 / 60)
    assert controller.settings.heating_step == pytest.approx(5.0 * 6 / 60)


# -- the happy path ---------------------------------------------------------

def test_a_full_series_runs_every_phase_of_every_cycle(qapp, clock):
    controller = make(clock, cycles=2)
    events = Recorder(controller)

    controller.start()
    run(controller, clock)

    assert controller.phase is Phase.DONE
    assert events.done == [True]
    assert events.started == [1, 2]
    assert events.finished == [1, 2]

    phases_of_cycle_1 = [p for p, c in events.phases if c == 1]
    assert phases_of_cycle_1 == [Phase.COOLING, Phase.HOLD_COLD, Phase.THAW,
                                 Phase.HOLD_WARM, Phase.SETTLE]


def test_the_setpoint_stays_between_the_limits(qapp, clock):
    controller = make(clock)
    events = Recorder(controller)

    controller.start()
    run(controller, clock)

    assert min(events.setpoints) == pytest.approx(-30.0)
    assert max(events.setpoints) == pytest.approx(10.0)


def test_recording_covers_the_cooling_ramp_only(qapp, clock):
    """cycle_started/cycle_finished must bracket exactly the cooling phase."""
    controller = make(clock, cycles=1)
    recorded_phases = set()

    controller.cycle_started.connect(
        lambda n: recorded_phases.add(controller.phase))
    controller.start()

    for _ in range(2000):
        if controller.phase.is_finished:
            break
        if controller.phase.is_recording:
            recorded_phases.add(controller.phase)
        controller.update_temperature(controller.setpoint)
        clock.advance(controller.settings.step_interval / 60.0)
        controller.tick()

    assert recorded_phases == {Phase.COOLING}


def test_an_unbounded_series_keeps_cycling(qapp, clock):
    controller = make(clock, cycles=None)
    events = Recorder(controller)

    controller.start()
    run(controller, clock, ticks=3000)

    assert not controller.phase.is_finished
    assert len(events.started) > 2


# -- the closed-loop holds --------------------------------------------------

def test_the_cold_hold_waits_for_the_bath_not_the_setpoint(qapp, clock):
    """The bath lags, so reaching the setpoint floor is not enough."""
    controller = make(clock, hold_cold_minutes=5.0)
    controller.start()

    # Cool down with the bath stuck 10 degC behind.
    for _ in range(500):
        controller.update_temperature(controller.setpoint + 10.0)
        clock.advance(0.1)
        controller.tick()
        if controller.phase is Phase.HOLD_COLD:
            break

    assert controller.phase is Phase.HOLD_COLD

    # The bath is still at -20 while freeze_temp is -30: no moving on.
    for _ in range(100):
        controller.update_temperature(-20.0)
        clock.advance(0.1)
        controller.tick()
    assert controller.phase is Phase.HOLD_COLD

    # The bath arrives; the dwell only starts counting now.
    controller.update_temperature(-30.0)
    controller.tick()
    assert controller.phase is Phase.HOLD_COLD

    clock.advance(4.0)
    controller.update_temperature(-30.0)
    controller.tick()
    assert controller.phase is Phase.HOLD_COLD, "left before the dwell elapsed"

    clock.advance(1.5)
    controller.update_temperature(-30.0)
    controller.tick()
    assert controller.phase is Phase.THAW


def test_a_hold_gives_up_after_the_timeout(qapp, clock):
    """Better to move on than to sit at the bottom of the ramp forever."""
    controller = make(clock, hold_timeout_minutes=30.0)
    controller.start()

    for _ in range(500):
        controller.update_temperature(controller.setpoint)
        clock.advance(0.1)
        controller.tick()
        if controller.phase is Phase.HOLD_COLD:
            break

    # The bath never gets cold enough.
    controller.update_temperature(-5.0)
    clock.advance(31.0)
    controller.tick()

    assert controller.phase is Phase.THAW


def test_the_next_cycle_waits_for_the_bath_to_come_back_up(qapp, clock):
    controller = make(clock, cycles=2)
    controller.start()

    while controller.phase is not Phase.SETTLE:
        controller.update_temperature(controller.setpoint)
        clock.advance(0.1)
        controller.tick()

    # Still warm from the thaw: the next scan must not start yet.
    for _ in range(50):
        controller.update_temperature(10.0)
        clock.advance(0.1)
        controller.tick()
    assert controller.phase is Phase.SETTLE
    assert controller.cycle == 1

    controller.update_temperature(0.0)
    controller.tick()
    assert controller.phase is Phase.COOLING
    assert controller.cycle == 2


# -- the watchdog -----------------------------------------------------------

def test_missed_readings_abort_the_series_at_a_safe_temperature(qapp, clock):
    controller = make(clock, max_missed_readings=5)
    events = Recorder(controller)
    controller.start()

    for _ in range(5):
        controller.update_temperature(None)

    assert controller.phase is Phase.ABORTED
    assert events.setpoints[-1] == SAFE_TEMPERATURE
    assert 'no valid chiller reading' in events.aborted[0]
    assert not controller.timer.isActive()


def test_a_good_reading_resets_the_watchdog(qapp, clock):
    controller = make(clock, max_missed_readings=5)
    controller.start()

    for _ in range(4):
        controller.update_temperature(None)
    controller.update_temperature(-1.0)
    for _ in range(4):
        controller.update_temperature(None)

    assert controller.phase is not Phase.ABORTED


def test_aborting_mid_scan_closes_the_open_cycle(qapp, clock):
    controller = make(clock)
    events = Recorder(controller)
    controller.start()

    assert controller.phase is Phase.COOLING
    controller.stop('user pressed abort')

    assert events.finished == [1], "the open folder was never closed"
    assert events.setpoints[-1] == SAFE_TEMPERATURE


def test_stopping_outside_a_scan_does_not_close_a_cycle(qapp, clock):
    controller = make(clock)
    events = Recorder(controller)
    controller.start()

    while controller.phase is not Phase.THAW:
        controller.update_temperature(controller.setpoint)
        clock.advance(0.1)
        controller.tick()

    events.finished.clear()
    controller.stop()

    assert events.finished == []
    assert controller.phase is Phase.DONE


# -- estimates --------------------------------------------------------------

def test_the_duration_estimate_is_in_the_right_ballpark(qapp, clock):
    controller = make(clock, scan_start_temp=0.0, min_temp=-45.0, freeze_temp=-45.0,
                      thaw_temp=10.0, cooling_rate=1.0, heating_rate=5.0,
                      hold_cold_minutes=10.0, hold_warm_minutes=10.0, cycles=50)

    per_cycle = controller.settings.estimated_cycle_seconds() / 60
    total = controller.settings.estimated_total_seconds() / 3600

    assert per_cycle == pytest.approx(45 + 11 + 20 + 2, abs=1)
    assert total == pytest.approx(65, abs=2)


# -- manual ramp mode -------------------------------------------------------

def manual(clock, **overrides):
    """The settings the 'Start ramp' button uses: no holds, no folders."""
    settings = SeriesSettings(
        scan_start_temp=0.0, min_temp=-30.0, freeze_temp=-30.0, thaw_temp=0.0,
        cooling_rate=60.0, heating_rate=60.0, hold_cold_minutes=0.0,
        hold_warm_minutes=0.0, cycles=None, folder_per_cycle=False,
        wait_for_bath=False, **overrides)
    return SeriesController(settings, clock=clock)


def test_the_manual_ramp_turns_around_without_waiting_for_the_bath(qapp, clock):
    """Regression: the manual ramp must behave as it always has."""
    controller = manual(clock)
    events = Recorder(controller)
    controller.start()

    # No temperature is ever fed in: it must keep cycling regardless.
    for _ in range(400):
        clock.advance(0.1)
        controller.tick()

    assert not controller.phase.is_finished
    assert len(events.started) > 2, "the ramp stopped instead of cycling"
    assert min(events.setpoints) == pytest.approx(-30.0)
    assert max(events.setpoints) == pytest.approx(0.0)


def test_the_setpoint_is_not_rewritten_while_it_does_not_move(qapp, clock):
    """During a hold the chiller should not get the same setpoint every tick."""
    controller = make(clock, hold_cold_minutes=10.0)
    events = Recorder(controller)
    controller.start()

    while controller.phase is not Phase.HOLD_COLD:
        controller.update_temperature(controller.setpoint)
        clock.advance(0.1)
        controller.tick()

    before = len(events.setpoints)
    for _ in range(50):
        controller.update_temperature(-30.0)
        clock.advance(0.05)
        controller.tick()

    assert len(events.setpoints) == before, "the setpoint was re-sent during the hold"


def test_the_first_setpoint_is_always_written(qapp, clock):
    """The chiller may hold any setpoint from a previous run."""
    controller = make(clock)
    events = Recorder(controller)

    controller.start()

    assert events.setpoints[0] == pytest.approx(controller.settings.scan_start_temp)
