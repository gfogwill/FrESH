"""Single source of truth for the sampling stations.

Both the metadata form and the experiment layer used to carry their own copy of
this table, and they had drifted apart (VKK, ODE and NYA existed only in
``src/experiment/experiment.py``, so the "search by label" button in the GUI
reported "Station not found" for them).
"""

STATIONS = {
    'WBG': {
        'station_name': 'Water background',
        'station_mapping': None,
        'sampler_id': None,
        'latitude': 0.0,
        'longitude': 0.0,
        'altitude': 0.0,
    },
    'HEL': {
        'station_name': 'Helsinki',
        'station_mapping': '01HELSINKI',
        'sampler_id': 'Z01',
        'latitude': 60.1699,
        'longitude': 24.9384,
        'altitude': 17.0,
    },
    'UTO': {
        'station_name': 'Utö',
        'station_mapping': '09UTÖ',
        'sampler_id': 'Z09',
        'latitude': 59.7763,
        'longitude': 21.4231,
        'altitude': 9.0,
    },
    'KUO': {
        'station_name': 'Kuopio',
        'station_mapping': '77KUOPIO',
        'sampler_id': 'Z77',
        'latitude': 62.8926,
        'longitude': 27.6770,
        'altitude': 75.0,
    },
    'PAL': {
        'station_name': 'Pallas',
        'station_mapping': '36PALLAS',
        'sampler_id': 'Z36',
        'latitude': 67.9674,
        'longitude': 24.1196,
        'altitude': 560.0,
    },
    'VKK': {
        'station_name': 'Viikki',
        'station_mapping': 'Vikki',
        'sampler_id': 'Z01',
        'latitude': 1.0,
        'longitude': 1.0,
        'altitude': 0.0,
    },
    'ODE': {
        'station_name': 'ODEN',
        'station_mapping': 'ODEN',
        'sampler_id': None,
        'latitude': 1.0,
        'longitude': 1.0,
        'altitude': 0.0,
    },
    'NYA': {
        'station_name': 'Ny Ålesund',
        'station_mapping': 'NYÅLESUND',
        'sampler_id': None,
        'latitude': 78.9067,
        'longitude': 11.8883,
        'altitude': 474.0,
    },
}

# Backwards-compatible alias: older code imported this name.
stations_dict = STATIONS


def station_code(label):
    """Return the 3-letter station code encoded in ``label`` (e.g. PAL20240619).

    Returns ``None`` when the label is empty or its prefix is not a known
    station.
    """
    if not label or len(label) < 3:
        return None

    code = label[0:3].upper()
    return code if code in STATIONS else None


def get_station(label):
    """Return the station entry for ``label``, or ``None`` if unknown."""
    code = station_code(label)
    return STATIONS[code] if code else None
