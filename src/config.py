"""Per-machine configuration.

FrESH runs on two PCs that differ mainly in which chiller is attached, so the
chiller model and the serial port live in an ``.ini`` file that is *not* under
version control.  The file is looked up in this order:

1. the path given to :func:`load_config`, or the ``FRESH_CONFIG`` env var
2. ``etc/fresh.<hostname>.ini``  -- per-PC file, the recommended one
3. ``etc/test.ini``              -- legacy name, still honoured
4. ``etc/fresh.default.ini``     -- template committed to the repo

Use :func:`get_config` to read it; it is parsed once and cached.
"""

import configparser
import logging
import os
import pathlib
import socket

from src import paths

DEFAULT_CONFIG_NAME = 'fresh.default.ini'
LEGACY_CONFIG_NAME = 'test.ini'

_config = None


def candidate_paths(explicit=None):
    """Return the config files to try, in priority order."""
    candidates = []

    if explicit:
        candidates.append(pathlib.Path(explicit))

    env_path = os.environ.get('FRESH_CONFIG')
    if env_path:
        candidates.append(pathlib.Path(env_path))

    hostname = socket.gethostname().split('.')[0]
    candidates.append(paths.etc_path / f'fresh.{hostname}.ini')
    candidates.append(paths.etc_path / LEGACY_CONFIG_NAME)
    candidates.append(paths.etc_path / DEFAULT_CONFIG_NAME)

    return candidates


def load_config(explicit=None):
    """Parse the first config file that exists and return it.

    Raises
    ------
    FileNotFoundError
        If none of the candidate files exist.
    """
    tried = []
    for candidate in candidate_paths(explicit):
        tried.append(str(candidate))
        if candidate.is_file():
            parser = configparser.ConfigParser(interpolation=None)
            parser.read(candidate, encoding='utf-8')
            logging.info(f"Configuration loaded from: {candidate}")
            return parser

    raise FileNotFoundError(
        "No FrESH configuration file found. Copy etc/{} to etc/fresh.{}.ini "
        "and adjust it. Tried: {}".format(
            DEFAULT_CONFIG_NAME, socket.gethostname().split('.')[0], ', '.join(tried)
        )
    )


def get_config(reload=False):
    """Return the cached configuration, loading it on first use."""
    global _config
    if _config is None or reload:
        _config = load_config()
    return _config


def get_chiller_model(config=None):
    """Return the chiller model configured for this machine (upper case)."""
    config = config if config is not None else get_config()
    return config['CHILLER']['MODEL'].strip().upper()
