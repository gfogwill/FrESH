FrESH
==============================

This project is to control the cooling unit, read the camara and get the Ice Nuclei concentration


# Installation

These instructions will give you a copy of the project up and running on
your local machine for development and testing purposes. 

### Prerequisites

Requirements for the software and other tools to build, test and push 
- [Python 3](https://www.python.org)
- [uldaq](https://github.com/mccdaq/uldaq)


## Getting Started

Clone the repository

```console
$ git clone https://github.fmi.fi/perezfo/FrESH
$ cd FrESH
```

Now let's install the requirements. But before we do that, we **strongly**
recommend creating a virtual environment with a tool such as
[virtualenv](https://virtualenv.pypa.io/en/stable/):

```console
$ python -m venv venv
$ source venv/bin/activate
$ make requirements
```

Every time you start a new session you need to activate the virtual environment.

```console
$ source venv/bin/activate
```

## Configuration

Each PC has its own chiller and serial port, so the machine-specific settings
live in an `.ini` file that is not under version control. Copy the template and
adjust it:

```console
$ cp etc/fresh.default.ini etc/fresh.$(hostname -s).ini
```

The important key is the chiller model (`RE1050`, `RP1845` or the deprecated
`RK20`) and the serial port of the ADAM module:

```ini
[SERIAL]
PORT      = /dev/ttyUSB1

[CHILLER]
MODEL     = RE1050
```

On a machine with more than one serial device -- the RE1050 has an ADAM module
on its own port besides the chiller -- also pin the chiller's port, otherwise it
is guessed:

```ini
[CHILLER]
MODEL     = RE1050
PORT      = /dev/ttyUSB0
```

To see what this machine has and which port would be used:

```console
$ python -m src.daq.ports
```

The file is looked up in this order, first match wins:

1. `$FRESH_CONFIG`
2. `etc/fresh.<hostname>.ini`
3. `etc/test.ini` (the old name, still honoured)
4. `etc/fresh.default.ini`

## Using the code

```console
$ python -m src.gui.main_gui
```

**New double** opens the metadata form for a pair of PCR plates; confirming it
opens the scan window, where you connect the camera and the chiller.
**View experiment** opens the analysis window.

### Running a scan

Connect the camera and the chiller, then either:

* **Start ramp** -- the setpoint cycles between the scan start temperature and
  the minimum until you stop it. Everything is recorded into one folder per
  plate. Tick **Save** to start recording.
* **Start series** -- an automated freeze/thaw series (below).

### Freeze/thaw series

A series repeats this cycle as many times as you ask:

| phase | what happens | recording |
|-------|--------------|-----------|
| cooling | the setpoint ramps down to the min. setpoint at the cooling rate | **yes** |
| hold cold | waits for the measured temperature to reach *Hold until*, then dwells | no |
| thaw | the setpoint ramps up to the thaw temperature | no |
| hold warm | waits for the bath to get warm, then dwells to melt the sample | no |
| settle | back to the scan start temperature | no |

The ramps are **open loop**: the setpoint marches at the rate you asked for and
the bath follows as best it can, so the cooling rate stays comparable with
earlier measurements. The **holds are closed loop**: because the bath lags the
setpoint badly at low temperature, the cold hold does not end until the measured
temperature has actually reached *Hold until*, and only then does the dwell
start counting. *measured on* picks which sensor decides that -- the bath (BT)
or the probe (RTD0).

*Hold until* is separate from the min. setpoint on purpose: you can drive the
setpoint to -45 but only wait for the bath to reach -35, for the case where the
chiller cannot actually get all the way down.

### Changing the settings while a series runs

The numbers in the *Freeze/thaw series* and *Ramp* boxes can be edited at any
time and are picked up **between cycles** -- never in the middle of one, so
every cycle runs with one consistent set of values. Watching the first cycle,
seeing everything freeze by -22 and shortening the minimum setpoint to -28 is
the normal way to use it; over fifty cycles that is hours saved.

The cycle count follows too, so a series can be extended or cut short while it
runs. What cannot change is the *mode*: whether each cycle gets its own folder
and whether the holds wait for the bath are fixed when the series starts.

A half-typed or impossible value is reported in the log and ignored, and the
series carries on with the settings it already had -- a typo in a text box must
not end a three-day run. Every change that is taken is logged and appended to
`settings_changes.log` in the series folder, so the record says which cycles ran
with which numbers.

Each cycle writes its own folder, `<timestamp>_<LABEL>_cNNN`, holding only the
cooling ramp -- so every cycle is a normal experiment that the analysis window
opens on its own. Pictures are deliberately not taken during the thaw: melting
is as big a grayscale jump as freezing, and the freezing detection would latch
onto the wrong one.

Series-level files go to `data/interim/<timestamp>_series/`:

* `series.json` -- the settings the series ran with
* `series.log` -- the whole run's log
* `series_sensors.csv` -- **continuous** readings, holds and thaw included, so
  you can check afterwards whether the chiller ever reached the temperature it
  was told to

If the chiller stops answering, the series stops itself and parks the setpoint
at 0 ºC. That is a backstop, not a licence to leave the rig alone: it is an
ethanol bath and somebody should be watching it.

> **Watch the analysis cutoff.** `process_sensors_data` and friends trim the
> record at `SENSOR_TEMPERATURE_FLOOR` (-45 ºC) and drop everything after the
> first crossing. If you scan that low, pass a lower `floor=` or the coldest
> part of your own data disappears. A warning is logged when rows are dropped.

## Analysing a set of experiments

Instead of opening each one in the analysis window, analyse a whole series at
once:

```console
$ python -m src.analysis.batch '202609180800_WBG*' --min-step auto
$ python -m src.analysis.figures data/processed/202609180800_WBG_wells.csv
```

The first command finds the wells **once** and reuses those positions for every
experiment in the set (detecting them per experiment lets the count come out at
95 or 97, and since wells are ordered by cutting the list into rows of 12, one
missing circle renumbers every well after it). It writes
`data/interim/<name>/freezing_temps.csv` per experiment and one combined table
with a row per well per experiment. The second turns that table into the
three-panel refreeze figure.

Two knobs decide what counts as a well freezing:

* `--min-step` -- the smallest change in grayscale that counts. **This is the
  one that matters.** `get_grayscales` subtracts the mean of the whole picture
  from every well, so each time one well freezes, every other well takes a small
  step in sympathy. That step is tiny in absolute terms but large compared with
  a well's own noise, so a purely statistical threshold lets it through. Pass
  `auto` to read the value off each experiment's data; the batch always prints
  what it would suggest.
* `--robust-z` -- how far the step must stand out from that well's own noise.

With neither, the largest step always wins and **every** well is declared
frozen, which is what the analysis window has always done. That is harmless for
a filter where all 96 freeze, and wrong for a water background, where most wells
never freeze and the frozen fraction would run up to 1.0 regardless.

`--t-start` and `--t-end` restrict the search to a temperature window, for the
spurious events that show up while the plate is still warm or right at the end.

`--max-simultaneous 0.25` rejects a frame that more than a quarter of the plate
was assigned to. Freezing is stochastic well by well, so forty wells sharing one
frame is the picture changing -- the plate moved, the camera re-exposed -- not
forty wells freezing at the same instant. The frame is blanked and the wells
that were on it are looked at again, so a well that really froze later is found
at its real temperature instead of being thrown away. The batch prints the
largest such group per experiment in its `same frame` column and flags it with
`!!` when it reaches a quarter of the plate.

Note that a *uniform* brightness change cannot cause this: `get_grayscales`
subtracts the mean of the picture from every well, so a flat shift cancels out
exactly. An artefact that survives that is geometric or uneven -- the plate or
camera moved, auto-exposure or auto-white-balance kicked in, something fogged
over. Turning off the camera's automatic exposure and white balance in the
camera settings window is worth doing before a long series.

## Troubleshooting

**"no reply from the chiller on /dev/ttyXXX for: bath temperature, setpoint, ..."**
The port being used is not the chiller's. Run `python -m src.daq.ports` and set
`[CHILLER] PORT` to the right one. On the RE1050 the ADAM module has its own
port, and opening it as the chiller's leaves both devices talking over one line:
the ADAM readings keep working while every chiller command comes back
unparseable.

## Running the tests

```console
$ make test
```

The tests drive real Qt widgets with the `offscreen` platform plugin, so they
need no display and no hardware attached.

--------

<p><small>Project based on the <a target="_blank" href="https://drivendata.github.io/cookiecutter-data-science/">cookiecutter data science project template</a>. #cookiecutterdatascience</small></p>

