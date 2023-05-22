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
$ git clone https://gitlab.fmi.fi/perezfo/icenucleicounter
$ cd icenucleicounter
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

## Using the code

```console
$ .
```

If everything is OK you should see the program logo.

--------

<p><small>Project based on the <a target="_blank" href="https://drivendata.github.io/cookiecutter-data-science/">cookiecutter data science project template</a>. #cookiecutterdatascience</small></p>

