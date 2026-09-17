"""Reading the sampler's raw summary ``.CSV`` files.

Given a label such as ``PAL20240619`` this locates the matching row in
``data/external/sampler_raw_data/<station_mapping>/*.CSV`` and turns it into an
:class:`~src.experiment.metadata.ExperimentMetadata`.

This used to exist twice -- once in ``src/gui/experiment_metadata.py`` and once
in ``src/experiment/experiment.py`` -- with different date handling, so the two
disagreed about which files they could read.  The GUI version (which accepts
both two- and four-digit years) is the one kept here.
"""

import logging
import os
from datetime import datetime

from src import paths
from src.experiment.metadata import ExperimentMetadata, TYPE_FILTER
from src.stations import get_station

# Accepted date spellings in the sampler files.
DATE_FORMATS = ("%d.%m.%Y", "%d.%m.%y")

# Column layout of the sampler summary CSV (';' separated).
COL_STATUS = 1
COL_START_DATE = 2
COL_START_TIME = 3
COL_END_DATE = 4
COL_END_TIME = 5
COL_FILTER_POSITION = 7
COL_AIR_VOLUME = 8
COL_FLOW = 9
COL_TEMP = 10
COL_PRESS = 11

# Defaults used for rows coming straight from the sampler.
DEFAULT_V_DROP = 5e-05
DEFAULT_V_WASH = 0.01


def parse_date(text):
    """Parse a sampler date, accepting both ``31.12.2024`` and ``31.12.24``.

    Returns ``None`` when the text matches none of the accepted formats.
    """
    text = (text or '').strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def parse_datetime(date_text, time_text):
    """Combine a sampler date and a ``HH:MM`` time into a ``datetime``."""
    date = parse_date(date_text)
    if date is None:
        return None
    try:
        return datetime.strptime(
            f"{date.strftime('%d.%m.%Y')} {time_text.strip()}", "%d.%m.%Y %H:%M"
        )
    except ValueError:
        return None


def label_date(label):
    """Return the date encoded in the label (the ``YYYYMMDD`` part)."""
    try:
        return datetime.strptime(label[3:], "%Y%m%d")
    except (ValueError, IndexError):
        return None


def sampler_data_dir(label):
    """Return the directory holding the sampler files for ``label``'s station."""
    station = get_station(label)
    if station is None:
        logging.error(f"Station not found for label: {label}")
        return None

    if not station['station_mapping']:
        # Water backgrounds and similar have no sampler directory.
        return None

    return paths.external_data_path / 'sampler_raw_data' / station['station_mapping']


def find_record(label):
    """Return the sampler CSV row matching ``label`` as a list of fields.

    Returns ``None`` when the station, the date or the file cannot be found.
    """
    directory = sampler_data_dir(label)
    if directory is None:
        return None

    wanted = label_date(label)
    if wanted is None:
        logging.warning(f"Label does not carry a valid date: {label}")
        return None

    if not os.path.isdir(directory):
        logging.warning(f"Sampler data directory not found: {directory}")
        return None

    for root, _dirs, files in os.walk(directory):
        for file_name in files:
            if not file_name.upper().endswith(".CSV"):
                continue

            csv_path = os.path.join(root, file_name)
            try:
                with open(csv_path, "r", encoding="utf-8-sig", errors="replace") as fo:
                    lines = fo.readlines()
            except OSError as e:
                logging.warning(f"Could not read {csv_path}: {e}")
                continue

            for line in lines[1:]:
                fields = line.strip().split(";")
                if len(fields) <= COL_START_DATE:
                    continue

                row_date = parse_date(fields[COL_START_DATE])
                if row_date is not None and row_date.date() == wanted.date():
                    logging.info(f"Sampler record for {label} found in {csv_path}")
                    return fields

    logging.warning(f"No raw data found for label: {label}")
    return None


def _to_float(fields, index):
    try:
        return float(fields[index].strip())
    except (IndexError, ValueError, AttributeError):
        return None


def _to_int(fields, index):
    try:
        return int(fields[index].strip())
    except (IndexError, ValueError, AttributeError):
        return None


def build_metadata(fields, label, experiment_type=TYPE_FILTER):
    """Build an :class:`ExperimentMetadata` from one sampler CSV row."""
    station = get_station(label)

    start = parse_datetime(fields[COL_START_DATE], fields[COL_START_TIME])
    end = parse_datetime(fields[COL_END_DATE], fields[COL_END_TIME])

    return ExperimentMetadata(
        station=label[0:3].upper(),
        experiment_type=experiment_type,
        label=label,
        sampler_id=station['sampler_id'] if station else None,
        sampler_status=fields[COL_STATUS].strip() if len(fields) > COL_STATUS else None,
        start_time=start.strftime("%Y-%m-%d %H:%M") if start else None,
        end_time=end.strftime("%Y-%m-%d %H:%M") if end else None,
        filter_position=_to_int(fields, COL_FILTER_POSITION),
        air_volume=_to_float(fields, COL_AIR_VOLUME),
        flow=_to_float(fields, COL_FLOW),
        temp=_to_float(fields, COL_TEMP),
        press=_to_float(fields, COL_PRESS),
        v_drop=DEFAULT_V_DROP,
        v_wash=DEFAULT_V_WASH,
        dil_factor=1.0,
        filter_fraction=1.0,
    )


def retrieve_metadata(label, experiment_type=TYPE_FILTER):
    """Look ``label`` up in the sampler files and return its metadata.

    Returns ``None`` when there is no matching record.
    """
    if not label:
        return None

    fields = find_record(label.upper())
    if fields is None:
        return None

    return build_metadata(fields, label.upper(), experiment_type)
