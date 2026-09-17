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

## Running the tests

```console
$ make test
```

The tests drive real Qt widgets with the `offscreen` platform plugin, so they
need no display and no hardware attached.

--------

<p><small>Project based on the <a target="_blank" href="https://drivendata.github.io/cookiecutter-data-science/">cookiecutter data science project template</a>. #cookiecutterdatascience</small></p>

