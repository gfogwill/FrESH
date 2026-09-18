"""The freeze/thaw series: a state machine that drives the chiller setpoint.

One *cycle* is five phases:

===============  =========================================  =========
phase            what it does                               recording
===============  =========================================  =========
``COOLING``      ramps the setpoint down to ``min_temp``    yes
``HOLD_COLD``    waits for the bath to reach                until the
                 ``freeze_temp``, then dwells               bath gets there
``THAW``         ramps the setpoint up to ``thaw_temp``     no
``HOLD_WARM``    waits for the bath to get warm, dwells     no
``SETTLE``       jumps back to ``scan_start_temp``          no
===============  =========================================  =========

Recording follows the **measured** temperature, not the setpoint. The bath lags,
so when the setpoint bottoms out the sample is still warmer than asked for and
wells are still freezing; stopping there would throw away the coldest and most
interesting part of every scan.

Two things are deliberate:

* The ramps are **open loop**. The setpoint marches at the requested rate and
  the bath follows as well as it can; the setpoint is never held back. That is
  how the existing measurements were taken, so the cooling rate stays
  comparable with them.
* The **holds are closed loop**. The bath lags the setpoint badly at low
  temperature, so waiting a fixed time would not guarantee the sample is
  actually cold. HOLD_COLD does not end until the measured bath temperature has
  reached ``freeze_temp``, and only then does the dwell start counting.

The controller owns no hardware and no thread. It is ticked by a timer and fed
temperature readings, and it answers with signals; :class:`ExperimentUi` is
what actually talks to the chiller. That keeps the whole sequence testable
without a chiller attached.
"""

import enum
import logging
import time
from dataclasses import dataclass

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

#: Where the setpoint is parked when a series is aborted. The bath is ethanol,
#: so the safe state is "not cold", not "off".
SAFE_TEMPERATURE = 0.0

#: How close to a target the bath must get for it to count as reached.
DEFAULT_TOLERANCE = 1.0

#: Seconds between setpoint steps.
DEFAULT_STEP_INTERVAL = 6

#: Consecutive failed readings before the watchdog gives up.
DEFAULT_MAX_MISSED_READINGS = 20


class Phase(enum.Enum):
    IDLE = 'idle'
    COOLING = 'cooling'
    HOLD_COLD = 'hold cold'
    THAW = 'thaw'
    HOLD_WARM = 'hold warm'
    SETTLE = 'settle'
    DONE = 'done'
    ABORTED = 'aborted'

    @property
    def is_finished(self):
        return self in (Phase.DONE, Phase.ABORTED)


@dataclass
class SeriesSettings:
    """Everything the operator sets before starting.

    Temperatures are degC, rates degC/min and holds minutes.
    """

    #: Where each scan starts, and where the bath returns between cycles.
    scan_start_temp: float = 0.0
    #: Lowest setpoint of the cooling ramp.
    min_temp: float = -35.0
    #: Bath temperature HOLD_COLD waits for. Usually equal to min_temp, but it
    #: can be set higher when the chiller cannot actually reach min_temp.
    freeze_temp: float = -35.0
    #: Setpoint the thaw ramps up to, to melt the sample.
    thaw_temp: float = 10.0

    cooling_rate: float = 1.0
    heating_rate: float = 5.0

    hold_cold_minutes: float = 10.0
    hold_warm_minutes: float = 10.0

    #: Number of cycles, or None to keep cycling until stopped.
    cycles: int = 50

    #: Give up waiting for the bath after this long and move on anyway.
    hold_timeout_minutes: float = 60.0

    tolerance: float = DEFAULT_TOLERANCE
    step_interval: float = DEFAULT_STEP_INTERVAL
    max_missed_readings: int = DEFAULT_MAX_MISSED_READINGS

    #: False for the manual ramp: keep cycling in one folder, recording always.
    folder_per_cycle: bool = True
    #: False for the manual ramp: turn around as soon as the setpoint reaches
    #: the limit, without waiting for the bath to catch up.
    wait_for_bath: bool = True

    def validate(self):
        """Raise ValueError if the settings could not produce a sane series."""
        if self.min_temp >= self.scan_start_temp:
            raise ValueError(f"Min. temp ({self.min_temp}) must be below the scan "
                             f"start temp ({self.scan_start_temp})")

        if self.thaw_temp <= self.min_temp:
            raise ValueError(f"Thaw temp ({self.thaw_temp}) must be above the "
                             f"min. temp ({self.min_temp})")

        if self.freeze_temp < self.min_temp - self.tolerance:
            raise ValueError(f"The bath cannot be asked to reach {self.freeze_temp} degC "
                             f"when the setpoint only goes down to {self.min_temp} degC")

        if self.freeze_temp >= self.scan_start_temp:
            raise ValueError(f"Freeze temp ({self.freeze_temp}) must be below the "
                             f"scan start temp ({self.scan_start_temp})")

        if self.cooling_rate <= 0 or self.heating_rate <= 0:
            raise ValueError("Cooling and heating rates must be greater than zero")

        if self.step_interval <= 0:
            raise ValueError("The step interval must be greater than zero")

        if self.cycles is not None and self.cycles < 1:
            raise ValueError("A series needs at least one cycle")

        if self.hold_cold_minutes < 0 or self.hold_warm_minutes < 0:
            raise ValueError("Hold times cannot be negative")

    @property
    def cooling_step(self):
        """degC per tick, from the degC/min the operator entered."""
        return abs(self.cooling_rate) * self.step_interval / 60.0

    @property
    def heating_step(self):
        return abs(self.heating_rate) * self.step_interval / 60.0

    def estimated_cycle_seconds(self):
        """Rough duration of one cycle, ignoring how far the bath lags."""
        cooling = (self.scan_start_temp - self.min_temp) / self.cooling_rate * 60
        thaw = (self.thaw_temp - self.min_temp) / self.heating_rate * 60
        holds = (self.hold_cold_minutes + self.hold_warm_minutes) * 60
        settle = 120  # the setpoint jumps; this is just the bath catching up
        return cooling + thaw + holds + settle

    def estimated_total_seconds(self):
        if self.cycles is None:
            return None
        return self.estimated_cycle_seconds() * self.cycles


class SeriesController(QObject):
    """Sequences the phases of a freeze/thaw series.

    The controller never touches the chiller. It emits :attr:`setpoint_changed`
    and whoever owns the hardware writes it.
    """

    #: A new setpoint should be written to the chiller.
    setpoint_changed = pyqtSignal(float)
    #: (phase, cycle number) -- the cycle number is 1-based.
    phase_changed = pyqtSignal(object, int)
    #: A cycle's cooling ramp is about to start; open its folder.
    cycle_started = pyqtSignal(int)
    #: A cycle's cooling ramp has ended; stop recording into its folder.
    cycle_finished = pyqtSignal(int)
    #: Every cycle requested has been run.
    series_finished = pyqtSignal()
    #: Something went wrong; the argument says what.
    aborted = pyqtSignal(str)

    def __init__(self, settings, parent=None, clock=time.monotonic):
        super().__init__(parent)

        settings.validate()
        self.settings = settings

        #: Injectable so the tests do not have to wait in real time.
        self._clock = clock

        self.phase = Phase.IDLE
        self.cycle = 0
        #: True while this cycle's pictures and readings are being kept.
        self.recording = False
        #: None until the first setpoint is written, so that the very first
        #: write always reaches the chiller whatever it was set to before.
        self.setpoint = None
        self.bath_temp = None

        self._phase_started_at = None
        self._target_reached_at = None
        self._missed_readings = 0

        self.timer = QTimer(self)
        self.timer.setInterval(int(settings.step_interval * 1000))
        self.timer.timeout.connect(self.tick)

    # -- lifecycle -----------------------------------------------------------

    def start(self):
        """Begin the first cycle."""
        if self.phase is not Phase.IDLE:
            logging.warning("The series is already running")
            return

        total = self.settings.estimated_total_seconds()
        if total is not None:
            logging.info(f"Starting a series of {self.settings.cycles} cycle(s), "
                         f"about {total / 3600:.1f} h in total")
        else:
            logging.info("Starting a continuous ramp; it runs until stopped")

        self.cycle = 0
        self._begin_cycle()
        self.timer.start()

    def stop(self, reason=None):
        """End the series early. The setpoint is parked at a safe temperature."""
        if self.phase.is_finished:
            return

        self.timer.stop()
        self._set_setpoint(SAFE_TEMPERATURE)

        self._end_recording()

        if reason is None:
            logging.info("Series stopped")
            self._enter(Phase.DONE)
            self.series_finished.emit()
        else:
            logging.error(f"Series aborted: {reason}")
            self._enter(Phase.ABORTED)
            self.aborted.emit(reason)

    # -- input ---------------------------------------------------------------

    def update_temperature(self, bath_temp):
        """Feed the controller the latest bath reading.

        Passing ``None`` counts as a missed reading; enough of them in a row
        abort the series.
        """
        if bath_temp is None:
            self._missed_readings += 1
            if self._missed_readings >= self.settings.max_missed_readings:
                self.stop(f"no valid chiller reading for "
                          f"{self._missed_readings} consecutive polls")
            return

        self._missed_readings = 0
        self.bath_temp = bath_temp

    # -- the state machine ---------------------------------------------------

    def tick(self):
        """Advance one step. Called by the timer, or by the tests directly."""
        if self.phase.is_finished or self.phase is Phase.IDLE:
            return

        handler = {
            Phase.COOLING: self._tick_cooling,
            Phase.HOLD_COLD: self._tick_hold_cold,
            Phase.THAW: self._tick_thaw,
            Phase.HOLD_WARM: self._tick_hold_warm,
            Phase.SETTLE: self._tick_settle,
        }[self.phase]

        handler()

    def _tick_cooling(self):
        # Open loop: the setpoint keeps stepping down whatever the bath does.
        if self.setpoint is None:
            # _begin_cycle always writes it first; this is just belt and braces.
            self._set_setpoint(self.settings.scan_start_temp)
            return

        if self.setpoint > self.settings.min_temp:
            self._set_setpoint(max(self.setpoint - self.settings.cooling_step,
                                   self.settings.min_temp))
            return

        # The setpoint has bottomed out, but the bath is still on its way down
        # and wells are still freezing, so keep recording into the hold.
        self._enter(Phase.HOLD_COLD)

    def _tick_hold_cold(self):
        reached = self._bath_at_or_below(self.settings.freeze_temp)

        if reached:
            # The sample is finally at the temperature that was asked for:
            # whatever was going to freeze on the way down has frozen.
            self._end_recording()

        if self._wait_for_bath(reached=reached,
                               dwell_minutes=self.settings.hold_cold_minutes,
                               what=f"the bath to reach {self.settings.freeze_temp} degC"):
            self._end_recording()   # also covers giving up on the timeout
            self._enter(Phase.THAW)

    def _tick_thaw(self):
        if self.setpoint < self.settings.thaw_temp:
            self._set_setpoint(min(self.setpoint + self.settings.heating_step,
                                   self.settings.thaw_temp))
            return

        self._enter(Phase.HOLD_WARM)

    def _tick_hold_warm(self):
        warm_enough = self.settings.thaw_temp - self.settings.tolerance
        if self._wait_for_bath(reached=self._bath_at_or_above(warm_enough),
                               dwell_minutes=self.settings.hold_warm_minutes,
                               what=f"the bath to reach {warm_enough:.1f} degC"):
            # Not a measurement phase, so jump rather than ramp: the chiller
            # gets back to the starting temperature as fast as it can.
            self._set_setpoint(self.settings.scan_start_temp)
            self._enter(Phase.SETTLE)

    def _tick_settle(self):
        back_at_start = self._bath_at_or_below(self.settings.scan_start_temp
                                               + self.settings.tolerance)

        if not self._wait_for_bath(reached=back_at_start, dwell_minutes=0,
                                   what=f"the bath to return to "
                                        f"{self.settings.scan_start_temp} degC"):
            return

        if self.settings.cycles is not None and self.cycle >= self.settings.cycles:
            self.timer.stop()
            self._enter(Phase.DONE)
            logging.info(f"Series finished: {self.cycle} cycle(s) completed")
            self.series_finished.emit()
            return

        self._begin_cycle()

    # -- helpers -------------------------------------------------------------

    def _begin_cycle(self):
        self.cycle += 1
        self._set_setpoint(self.settings.scan_start_temp)
        self._enter(Phase.COOLING)
        self.recording = True
        self.cycle_started.emit(self.cycle)

    def _end_recording(self):
        """Close this cycle's folder. Safe to call more than once."""
        if not self.recording:
            return

        self.recording = False
        logging.info(f"Cycle {self.cycle}: recording stopped "
                     f"(measured {self.bath_temp} degC)")
        self.cycle_finished.emit(self.cycle)

    def _enter(self, phase):
        self.phase = phase
        self._phase_started_at = self._clock()
        self._target_reached_at = None

        if not phase.is_finished:
            logging.info(f"Cycle {self.cycle}: {phase.value}")

        self.phase_changed.emit(phase, self.cycle)

    def _set_setpoint(self, value):
        value = round(value, 2)
        if value == self.setpoint:
            return  # the chiller already has it

        self.setpoint = value
        self.setpoint_changed.emit(self.setpoint)

    def _bath_at_or_below(self, target):
        return self.bath_temp is not None and self.bath_temp <= target

    def _bath_at_or_above(self, target):
        return self.bath_temp is not None and self.bath_temp >= target

    def _wait_for_bath(self, reached, dwell_minutes, what):
        """Return True once the bath got there and the dwell has elapsed.

        Gives up (and returns True) after ``hold_timeout_minutes``, because
        moving on is safer than sitting at the bottom of the ramp forever.
        """
        now = self._clock()

        if not self.settings.wait_for_bath:
            reached = True

        if reached:
            if self._target_reached_at is None:
                self._target_reached_at = now
                if dwell_minutes:
                    logging.info(f"Cycle {self.cycle}: target reached, "
                                 f"holding for {dwell_minutes:g} min")

            if now - self._target_reached_at >= dwell_minutes * 60:
                return True
            return False

        waited = now - self._phase_started_at
        if waited >= self.settings.hold_timeout_minutes * 60:
            logging.warning(f"Cycle {self.cycle}: gave up waiting for {what} after "
                            f"{waited / 60:.0f} min (bath is at {self.bath_temp}); "
                            f"moving on")
            return True

        return False

    # -- for the GUI ---------------------------------------------------------

    def status_text(self):
        """One line describing where the series is, for the status label."""
        if self.phase is Phase.IDLE:
            return "Idle"
        if self.phase is Phase.DONE:
            return f"Finished — {self.cycle} cycle(s)"
        if self.phase is Phase.ABORTED:
            return f"ABORTED at cycle {self.cycle}"

        total = self.settings.cycles
        counter = f"Cycle {self.cycle}/{total}" if total else f"Cycle {self.cycle}"
        bath = f"{self.bath_temp:.1f}" if self.bath_temp is not None else "?"

        setpoint = f"{self.setpoint:.1f}" if self.setpoint is not None else "?"

        return f"{counter} · {self.phase.value} · SP {setpoint} / bath {bath} °C"
