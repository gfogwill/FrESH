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


def test_recording_follows_the_bath_not_the_setpoint(qapp, clock):
    """Regression: recording stopped the moment the SETPOINT bottomed out.

    The bath lags, so at that moment the sample is still warmer than asked for
    and wells are still freezing. Stopping there threw away the coldest part of
    every scan.
    """
    controller = make(clock, hold_cold_minutes=5.0)
    events = Recorder(controller)
    controller.start()

    # Cool down with the bath stuck 10 degC behind the setpoint.
    while controller.phase is Phase.COOLING:
        controller.update_temperature(controller.setpoint + 10.0)
        clock.advance(0.1)
        controller.tick()

    assert controller.phase is Phase.HOLD_COLD
    assert controller.recording, "stopped recording while the bath was still falling"
    assert events.finished == []

    # Still on its way down: keep recording.
    for _ in range(20):
        controller.update_temperature(-25.0)
        clock.advance(0.1)
        controller.tick()
    assert controller.recording
    assert events.finished == []

    # The bath arrives at the temperature that was asked for.
    controller.update_temperature(-30.0)
    controller.tick()

    assert not controller.recording
    assert events.finished == [1]


def test_recording_stops_before_the_thaw_even_if_the_bath_never_arrives(qapp, clock):
    """The hold can time out; the folder must still be closed."""
    controller = make(clock, hold_timeout_minutes=30.0)
    events = Recorder(controller)
    controller.start()

    while controller.phase is Phase.COOLING:
        controller.update_temperature(0.0)
        clock.advance(0.1)
        controller.tick()

    controller.update_temperature(-5.0)   # never gets cold
    clock.advance(31.0)
    controller.tick()

    assert controller.phase is Phase.THAW
    assert not controller.recording
    assert events.finished == [1]


def test_nothing_is_recorded_during_the_thaw(qapp, clock):
    """Melting is as big a grayscale jump as freezing; it must not be filmed."""
    controller = make(clock, cycles=1)
    recorded_phases = set()

    controller.start()
    for _ in range(2000):
        if controller.phase.is_finished:
            break
        if controller.recording:
            recorded_phases.add(controller.phase)
        controller.update_temperature(controller.setpoint)
        clock.advance(controller.settings.step_interval / 60.0)
        controller.tick()

    assert recorded_phases <= {Phase.COOLING, Phase.HOLD_COLD}
    assert Phase.THAW not in recorded_phases
    assert Phase.HOLD_WARM not in recorded_phases


def test_a_cycle_is_closed_exactly_once(qapp, clock):
    controller = make(clock, cycles=3)
    events = Recorder(controller)

    controller.start()
    run(controller, clock)

    assert events.finished == [1, 2, 3]


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


# -- changing the settings while the series runs ----------------------------

def following(clock, form, **overrides):
    """A controller that re-reads `form` (a dict) between cycles."""
    def provider():
        return SeriesSettings(**form)

    settings = SeriesSettings(**{**form, **overrides})
    return SeriesController(settings, clock=clock, settings_provider=provider)


BASE_FORM = dict(scan_start_temp=0.0, min_temp=-45.0, freeze_temp=-45.0,
                 thaw_temp=10.0, cooling_rate=60.0, heating_rate=60.0,
                 hold_cold_minutes=0.0, hold_warm_minutes=0.0, cycles=3)


def test_a_change_made_during_a_cycle_applies_to_the_next_one(qapp, clock):
    """Watch cycle 1 reach -22, shorten the ramp, and cycle 2 stops earlier."""
    form = dict(BASE_FORM)
    controller = following(clock, form)
    events = Recorder(controller)
    controller.start()

    # Cycle 1 runs to -45 as configured.
    while controller.cycle == 1 and not controller.phase.is_finished:
        controller.update_temperature(controller.setpoint)
        clock.advance(0.1)
        controller.tick()
        if controller.cycle == 1 and controller.phase is Phase.THAW:
            assert min(events.setpoints) == pytest.approx(-45.0)
            form['min_temp'] = form['freeze_temp'] = -28.0   # operator edits

    # From cycle 2 on, the ramp stops at -28.
    cycle2 = []
    controller.setpoint_changed.connect(cycle2.append)
    while controller.cycle == 2 and not controller.phase.is_finished:
        controller.update_temperature(controller.setpoint)
        clock.advance(0.1)
        controller.tick()

    assert controller.settings.min_temp == -28.0
    assert min(cycle2) == pytest.approx(-28.0), "cycle 2 still went past -28"


def test_the_change_is_announced(qapp, clock):
    form = dict(BASE_FORM)
    controller = following(clock, form)
    announced = []
    controller.settings_changed.connect(announced.append)
    controller.start()

    form['min_temp'] = form['freeze_temp'] = -28.0
    run(controller, clock, ticks=400)

    assert announced, "the operator got no confirmation"
    assert 'min_temp -45.0 -> -28.0' in announced[0]


def test_a_broken_form_never_stops_the_series(qapp, clock):
    """A typo in a text box must not end a three-day run."""
    form = dict(BASE_FORM)
    controller = following(clock, form)
    controller.start()

    form['min_temp'] = 5.0      # above the scan start: impossible
    run(controller, clock, ticks=800)

    assert controller.settings.min_temp == -45.0, "the impossible value was taken"
    assert not controller.phase is Phase.ABORTED


def test_a_provider_that_raises_never_stops_the_series(qapp, clock, caplog):
    def explode():
        raise ValueError("Min. setpoint is not a valid number: 'abc'")

    controller = SeriesController(SeriesSettings(**BASE_FORM), clock=clock,
                                  settings_provider=explode)
    controller.start()
    run(controller, clock, ticks=800)

    assert 'carrying on with the ones in use' in caplog.text
    assert controller.settings.min_temp == -45.0


def test_the_mode_cannot_be_changed_mid_series(qapp, clock):
    """folder_per_cycle and wait_for_bath define the run, not its numbers."""
    form = dict(BASE_FORM, folder_per_cycle=True, wait_for_bath=True)
    controller = following(clock, form)
    controller.start()

    form['folder_per_cycle'] = False
    form['wait_for_bath'] = False
    form['min_temp'] = form['freeze_temp'] = -28.0
    run(controller, clock, ticks=400)

    assert controller.settings.folder_per_cycle is True
    assert controller.settings.wait_for_bath is True
    assert controller.settings.min_temp == -28.0, "the numbers should still follow"


def test_the_series_can_be_extended_while_it_runs(qapp, clock):
    form = dict(BASE_FORM, cycles=2)
    controller = following(clock, form)
    events = Recorder(controller)
    controller.start()

    form['cycles'] = 4
    run(controller, clock)

    assert events.started == [1, 2, 3, 4]


def test_the_series_can_be_cut_short_while_it_runs(qapp, clock):
    form = dict(BASE_FORM, cycles=5)
    controller = following(clock, form)
    events = Recorder(controller)
    controller.start()

    form['cycles'] = 2
    run(controller, clock)

    assert events.started == [1, 2]
    assert events.done == [True]


def test_without_a_provider_nothing_changes(qapp, clock):
    controller = make(clock, cycles=2)
    controller.start()
    run(controller, clock)

    assert controller.settings.min_temp == -30.0


def test_the_tick_timer_is_left_alone_unless_its_own_setting_changed(qapp, clock):
    """setInterval restarts the countdown; do not do it for unrelated edits."""
    form = dict(BASE_FORM)
    controller = following(clock, form)
    controller.timer.setInterval(30)          # as a caller may have tuned it

    controller.start()
    form['min_temp'] = form['freeze_temp'] = -28.0
    controller._refresh_settings()

    assert controller.settings.min_temp == -28.0
    assert controller.timer.interval() == 30, "an unrelated edit reset the timer"


def test_changing_the_step_interval_does_move_the_timer(qapp, clock):
    form = dict(BASE_FORM)
    controller = following(clock, form)
    controller.start()

    form['step_interval'] = 12
    controller._refresh_settings()

    assert controller.timer.interval() == 12000


# -- the ramp must actually run at the rate it was given ---------------------

def measured_rate(qapp, rate, span=30.0):
    """Drive a cooling ramp and work out the rate it really ran at."""
    controller = SeriesController(SeriesSettings(
        scan_start_temp=0.0, min_temp=-span, freeze_temp=-span, thaw_temp=10.0,
        cooling_rate=rate, cycles=1))
    controller.start()

    ticks = 0
    while controller.phase is Phase.COOLING and ticks < 300_000:
        controller.tick()
        ticks += 1

    assert controller.phase is not Phase.COOLING, "the ramp never reached the floor"
    minutes = ticks * controller.settings.step_interval / 60.0
    return span / minutes


@pytest.mark.parametrize('rate', [1.0, 0.3, 0.25, 0.15, 0.12, 0.1, 0.09, 0.07, 0.05, 0.02])
def test_the_ramp_runs_at_the_rate_it_was_asked_for(qapp, rate):
    """Regression: the setpoint was accumulated from its own rounded value.

    The chiller takes two decimals, so the step was being quantised: 0.07
    degC/min actually ran at 0.1 (+43%), and at 0.05 the step disappeared into
    the rounding entirely and the ramp stopped moving -- with no timeout on the
    cooling phase, that hangs a weekend run forever.
    """
    assert measured_rate(qapp, rate) == pytest.approx(rate, rel=0.01)


def test_the_chiller_still_only_gets_two_decimals(qapp, clock):
    controller = make(clock, cooling_rate=0.07)
    written = []
    controller.setpoint_changed.connect(written.append)
    controller.start()

    for _ in range(50):
        controller.tick()

    assert all(value == round(value, 2) for value in written)


def test_the_ramp_keeps_its_exact_position_between_steps(qapp, clock):
    """Otherwise a step smaller than 0.005 degC rounds away to nothing."""
    controller = make(clock, cooling_rate=0.03)
    controller.start()

    start = controller.ramp_position
    for _ in range(10):
        controller.tick()

    moved = start - controller.ramp_position
    assert moved == pytest.approx(10 * controller.settings.cooling_step, rel=1e-6)


# -- a different cooling rate per cycle --------------------------------------

def test_the_rates_interleave_across_the_cycles(qapp, clock):
    """1 / 0.3 / 0.1 repeating, so any drift hits all three equally."""
    settings = SeriesSettings(scan_start_temp=0.0, min_temp=-30.0, freeze_temp=-30.0,
                              thaw_temp=10.0, cooling_rates=(1.0, 0.3, 0.1))

    assert [settings.rate_for_cycle(n) for n in range(1, 8)] == \
        [1.0, 0.3, 0.1, 1.0, 0.3, 0.1, 1.0]


def test_without_a_schedule_every_cycle_uses_the_single_rate(qapp, clock):
    settings = SeriesSettings(cooling_rate=0.5)

    assert [settings.rate_for_cycle(n) for n in (1, 2, 9)] == [0.5, 0.5, 0.5]


def test_each_cycle_actually_runs_at_its_own_rate(qapp, clock):
    """Not just bookkeeping: the ramp has to take longer at the slower rate."""
    controller = SeriesController(SeriesSettings(
        scan_start_temp=0.0, min_temp=-5.0, freeze_temp=-5.0, thaw_temp=5.0,
        cooling_rates=(1.0, 0.5), heating_rate=60.0,
        hold_cold_minutes=0.0, hold_warm_minutes=0.0, cycles=2,
        wait_for_bath=False), clock=clock)

    ticks_per_cycle = {}
    controller.start()
    for _ in range(5000):
        if controller.phase.is_finished:
            break
        if controller.phase is Phase.COOLING:
            ticks_per_cycle[controller.cycle] = ticks_per_cycle.get(controller.cycle, 0) + 1
        clock.advance(0.1)
        controller.tick()

    assert controller.cooling_rate in (1.0, 0.5)
    assert ticks_per_cycle[2] == pytest.approx(2 * ticks_per_cycle[1], rel=0.05)


def test_a_rate_of_zero_in_the_schedule_is_rejected(qapp):
    with pytest.raises(ValueError, match='greater than zero'):
        SeriesSettings(cooling_rates=(1.0, 0.0)).validate()


# -- the fast approach -------------------------------------------------------

def test_the_approach_is_fast_and_the_assay_stretch_is_not(qapp, clock):
    controller = SeriesController(SeriesSettings(
        scan_start_temp=0.0, min_temp=-10.0, freeze_temp=-10.0, thaw_temp=5.0,
        cooling_rate=0.1, approach_temp=-5.0, approach_rate=5.0), clock=clock)
    controller.start()

    fast = controller.cooling_step_now(-1.0)
    slow = controller.cooling_step_now(-6.0)

    assert fast == pytest.approx(5.0 * 6 / 60)
    assert slow == pytest.approx(0.1 * 6 / 60)


def test_the_approach_lands_exactly_on_its_temperature(qapp, clock):
    """Otherwise a fast step overshoots into the measured stretch."""
    controller = SeriesController(SeriesSettings(
        scan_start_temp=0.0, min_temp=-10.0, freeze_temp=-10.0, thaw_temp=5.0,
        cooling_rate=0.1, approach_temp=-5.0, approach_rate=5.0), clock=clock)
    controller.start()

    while controller.ramp_position > -5.0:
        controller.tick()

    assert controller.ramp_position == pytest.approx(-5.0)


def test_the_approach_saves_the_time_it_is_there_to_save(qapp, clock):
    """0 to -30 at 0.1 degC/min is five hours; from -5 it is a lot less."""
    slow = SeriesSettings(scan_start_temp=0.0, min_temp=-30.0, freeze_temp=-30.0,
                          thaw_temp=10.0, cooling_rate=0.1)
    quick = SeriesSettings(scan_start_temp=0.0, min_temp=-30.0, freeze_temp=-30.0,
                           thaw_temp=10.0, cooling_rate=0.1,
                           approach_temp=-5.0, approach_rate=5.0)

    assert slow.cooling_seconds_at(0.1) == pytest.approx(5 * 3600)
    assert quick.cooling_seconds_at(0.1) == pytest.approx(250 * 60 + 60)


@pytest.mark.parametrize('approach', [5.0, -40.0])
def test_an_approach_outside_the_ramp_is_rejected(qapp, approach):
    with pytest.raises(ValueError, match='must lie between'):
        SeriesSettings(scan_start_temp=0.0, min_temp=-30.0, freeze_temp=-30.0,
                       thaw_temp=10.0, approach_temp=approach).validate()


def test_the_estimate_averages_over_the_schedule(qapp):
    settings = SeriesSettings(scan_start_temp=0.0, min_temp=-30.0, freeze_temp=-30.0,
                              thaw_temp=10.0, cooling_rates=(1.0, 0.3, 0.1),
                              heating_rate=5.0, hold_cold_minutes=0.0,
                              hold_warm_minutes=0.0, cycles=21)

    per_cycle = [settings.estimated_cycle_seconds(n) for n in (1, 2, 3)]

    assert settings.estimated_cycle_seconds() == pytest.approx(sum(per_cycle) / 3)
    assert per_cycle[2] > per_cycle[0], "the slow cycle must take longer"
