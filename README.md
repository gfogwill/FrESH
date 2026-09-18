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
opens the scan window, where you connect the camera and the chiller and run the
temperature ramp. **View experiment** opens the analysis window.

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

