"""The temperature ramp (src/gui/threads.py)."""

import pytest

from src.gui.threads import TempThread


def run_ramp(temp_thread, steps):
    """Drive update_temp() by hand and collect the setpoints it emits."""
    emitted = []
    temp_thread.temp_signal.connect(emitted.append)
    temp_thread.quit = lambda: None  # the thread was never started
    for _ in range(steps):
        temp_thread.update_temp()
    return emitted


@pytest.mark.parametrize('cooling_rate', [1.0, 0.7, 0.33])
def test_ramp_turns_around_at_the_limits(qapp, cooling_rate):
    """Regression: the ramp used to die at the bottom of the cycle.

    Overshooting min_temp by any amount emitted a setpoint of 0 and terminated
    the thread, so unless the span was an exact multiple of the step, the
    heating half of the scan never ran.
    """
    ramp = TempThread(max_temp=0.0, min_temp=-30.0,
                      cooling_rate=cooling_rate, heating_rate=5.0)

    setpoints = run_ramp(ramp, steps=1200)

    assert min(setpoints) >= -30.0, "the setpoint went below min_temp"
    assert max(setpoints) <= 0.0, "the setpoint went above max_temp"
    assert min(setpoints) == pytest.approx(-30.0), "min_temp was never reached"
    assert ramp.completed_cycles >= 1, "the ramp never heated back up"


def test_rates_are_degrees_per_minute(qapp):
    """The GUI is labelled degC/min; a step is STEP_INTERVAL seconds long."""
    ramp = TempThread(0.0, -30.0, cooling_rate=1.0, heating_rate=5.0)

    assert ramp.chill_temp_step == pytest.approx(1.0 * TempThread.STEP_INTERVAL / 60)
    assert ramp.heat_temp_step == pytest.approx(5.0 * TempThread.STEP_INTERVAL / 60)


def test_stops_after_the_requested_cycles(qapp):
    ramp = TempThread(0.0, -1.0, cooling_rate=10.0, heating_rate=10.0, cycles=1)
    stopped = []
    ramp.quit = lambda: stopped.append(True)

    for _ in range(200):
        ramp.update_temp()

    assert ramp.completed_cycles >= 1
    assert stopped, "the ramp did not stop after the requested cycle"


@pytest.mark.parametrize('kwargs', [
    dict(max_temp=-30.0, min_temp=0.0, cooling_rate=1.0, heating_rate=5.0),
    dict(max_temp=0.0, min_temp=-30.0, cooling_rate=0.0, heating_rate=5.0),
])
def test_impossible_ramps_are_rejected(qapp, kwargs):
    with pytest.raises(ValueError):
        TempThread(**kwargs)
