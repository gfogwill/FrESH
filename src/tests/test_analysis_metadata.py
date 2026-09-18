"""Metadata round-trip through the analysis window (src/gui/analysis.py)."""

import json

import pytest

from src.experiment.experiment import FrESHExperiment, normalise_empty
from src.experiment.metadata import ExperimentMetadata
from src.gui.analysis import ExperimentAnalysisUi, parse_field, widget_text


@pytest.fixture
def analysis(qapp, raw_data_dir):
    return ExperimentAnalysisUi()


@pytest.fixture
def dateless(raw_data_dir):
    """An experiment whose start and end time were never filled in."""
    experiment = FrESHExperiment('202406190800_NOFECHA')
    experiment.set_metadata(ExperimentMetadata(
        label='NOFECHA', experiment_type='Filter', start_time=None, end_time=None,
        air_volume=1234.5, v_drop=5e-05))
    return experiment


# -- the conversions --------------------------------------------------------

def test_a_missing_value_shows_as_an_empty_field():
    """Regression: it used to show the literal text 'None'."""
    assert widget_text(None) == ''


@pytest.mark.parametrize('text, expected', [
    ('2024-06-19 08:00', '2024-06-19 08:00'),
    ('2024-06-19', '2024-06-19 00:00'),
    ('19.06.2024 08:00', '2024-06-19 08:00'),
    ('', None),
    ('   ', None),
    ('None', None),
])
def test_dates_are_read_back_leniently(text, expected):
    assert parse_field('start_time', text) == expected


def test_an_unparseable_date_is_reported_not_raised(caplog):
    """Regression: 'None' in the field raised ValueError and blocked saving."""
    assert parse_field('start_time', 'ayer') is None
    assert 'is not a date' in caplog.text


@pytest.mark.parametrize('name, text, expected', [
    ('air_volume', '21307.4', 21307.4),
    ('air_volume', '', None),
    ('filter_position', '7', 7),
    ('filter_position', '7.0', 7),
    ('label', 'PAL20240619', 'PAL20240619'),
])
def test_values_come_back_as_their_own_type(name, text, expected):
    assert parse_field(name, text) == expected


def test_a_bad_number_does_not_stop_the_form_being_saved(caplog):
    assert parse_field('air_volume', 'mucho') is None
    assert 'is not a number' in caplog.text


# -- the round trip ---------------------------------------------------------

def test_an_experiment_without_dates_can_be_saved(analysis, dateless):
    """Regression: this is what forced typing a dummy date to save at all."""
    analysis.experiment = dateless
    analysis.exp_name = dateless.exp_name

    analysis.load_metadata_into_gui(dateless.metadata)

    assert analysis.start_time_text_edit.text() == ''
    assert analysis.end_time_text_edit.text() == ''

    analysis.save()  # used to raise ValueError: time data 'None'

    stored = json.loads((dateless.experiment_path / 'metadata.json').read_text())
    assert stored['start_time'] is None
    assert stored['end_time'] is None


def test_the_round_trip_keeps_the_values(analysis, raw_data_dir):
    experiment = FrESHExperiment('202406190800_PAL20240619')
    experiment.set_metadata(ExperimentMetadata(
        label='PAL20240619', experiment_type='Filter', station='PAL',
        start_time='2024-06-19 08:00', end_time='2024-06-20 08:00',
        air_volume=21307.4, filter_position=7, v_drop=5e-05, v_wash=0.01,
        exp_description='una muestra'))
    analysis.experiment = experiment
    analysis.exp_name = experiment.exp_name

    analysis.load_metadata_into_gui(experiment.metadata)
    metadata = analysis.load_metadata_from_gui()

    assert metadata.label == 'PAL20240619'
    assert metadata.start_time == '2024-06-19 08:00'
    assert metadata.end_time == '2024-06-20 08:00'
    assert metadata.air_volume == 21307.4
    assert metadata.filter_position == 7
    assert metadata.exp_description == 'una muestra'


def test_filling_the_form_does_not_mark_it_modified(analysis, dateless):
    """Showing an experiment is not editing it."""
    analysis.experiment = dateless
    analysis.metadata_modified = False

    analysis.load_metadata_into_gui(dateless.metadata)

    assert not analysis.metadata_modified


def test_editing_a_field_is_stored_with_its_type(analysis, dateless):
    analysis.experiment = dateless

    analysis.air_volume_text_edit.setText('999.5')

    assert dateless.metadata.air_volume == 999.5


def test_typing_before_loading_an_experiment_does_not_crash(analysis):
    """The widgets are wired up in __init__ now, so this path is reachable."""
    analysis.experiment = None

    analysis.air_volume_text_edit.setText('1')  # must not raise


def test_loading_several_experiments_does_not_stack_connections(analysis, dateless):
    """Each load used to add one more connection, so edits fired N times."""
    analysis.experiment = dateless
    calls = []
    original = analysis.update_metadata
    analysis.update_metadata = lambda *a: (calls.append(a), original(*a))[1]

    for _ in range(4):
        analysis.load_metadata_into_gui(dateless.metadata)

    analysis.air_volume_text_edit.setText('42')

    assert len([c for c in calls if c[0] == 'air_volume']) == 1


# -- older files ------------------------------------------------------------

@pytest.mark.parametrize('stored, expected', [
    ('None', None), ('', None), ('null', None), ('  none  ', None),
    ('PAL20240619', 'PAL20240619'), (21307.4, 21307.4), (None, None),
])
def test_placeholders_in_older_files_load_as_missing(stored, expected):
    assert normalise_empty(stored) == expected


def test_a_description_is_not_mangled_by_the_placeholder_cleanup():
    """The old cleanup ran str.replace over the raw JSON text."""
    text = 'the "None" case, and an empty "" one'

    assert normalise_empty(text) == text


def test_an_old_file_with_none_strings_loads_as_missing(raw_data_dir):
    folder = raw_data_dir / '202406190800_VIEJO'
    (folder / 'pics').mkdir(parents=True)
    (folder / 'metadata.json').write_text(json.dumps({
        'label': 'VIEJO', 'experiment_type': 'Filter',
        'start_time': 'None', 'end_time': '', 'air_volume': 100.0}))

    experiment = FrESHExperiment('202406190800_VIEJO')

    assert experiment.metadata.air_volume == 100.0


# -- the metadata object ----------------------------------------------------

def test_only_the_timestamp_that_is_set_gets_converted():
    """One try block covered both, so end_time was skipped and stayed a datetime."""
    from datetime import datetime

    metadata = ExperimentMetadata(label='X', start_time=None,
                                  end_time=datetime(2024, 6, 20, 8, 0))

    metadata.check_required_fields()

    assert metadata.start_time is None
    assert metadata.end_time == '2024-06-20 08:00'
    json.dumps(metadata.__dict__)  # must be serialisable


# -- the background dropdown ------------------------------------------------

def background(raw_data_dir, name, experiment_type):
    """A processed experiment of the given type, as the dropdown sees it."""
    from src import paths

    (paths.processed_data_path / name).mkdir(parents=True, exist_ok=True)
    folder = raw_data_dir / name
    (folder / 'pics').mkdir(parents=True, exist_ok=True)
    (folder / 'metadata.json').write_text(json.dumps(
        {'label': name, 'experiment_type': experiment_type}))


def test_field_backgrounds_show_up_in_the_dropdown(analysis, raw_data_dir):
    """Regression: the set spelled it 'Field backgrouund', so they never did."""
    background(raw_data_dir, '202406190800_CAMPO', 'Field background')

    assert analysis.filter_background_folders() == ['202406190800_CAMPO']


@pytest.mark.parametrize('experiment_type, listed', [
    ('Water background', True),
    ('Filter background', True),
    ('Punched filter background', True),
    ('Field background', True),
    ('filter background', True),   # matching is case insensitive
    ('Filter', False),
    ('Punched filter', False),
])
def test_only_background_types_are_offered(analysis, raw_data_dir, experiment_type, listed):
    background(raw_data_dir, '202406190800_X', experiment_type)

    assert bool(analysis.filter_background_folders()) is listed


def test_an_unreadable_metadata_file_is_skipped_not_fatal(analysis, raw_data_dir, caplog):
    from src import paths

    background(raw_data_dir, '202406190800_BUENO', 'Water background')
    (paths.processed_data_path / '202406190800_ROTO').mkdir(parents=True)
    roto = raw_data_dir / '202406190800_ROTO'
    (roto / 'pics').mkdir(parents=True)
    (roto / 'metadata.json').write_text('{ no es json')

    assert analysis.filter_background_folders() == ['202406190800_BUENO']
    assert 'Could not read the metadata' in caplog.text
