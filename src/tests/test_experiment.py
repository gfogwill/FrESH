"""FrESHExperiment (src/experiment/experiment.py)."""

import json

import pytest

from src import paths
from src.experiment.experiment import FrESHExperiment
from src.experiment.metadata import ExperimentMetadata


def test_creating_a_new_experiment_does_not_need_metadata(raw_data_dir):
    """Regression: 'NoneType' object has no attribute 'station'.

    __init__ validated the metadata unconditionally, but a brand new
    experiment only gets its metadata afterwards, from set_metadata().
    """
    experiment = FrESHExperiment('202406190800_PAL20240619')

    assert experiment.metadata is None
    assert experiment.experiment_path.is_dir()
    assert experiment.pics_path.is_dir()


def test_directories_are_created_even_if_the_parents_are_missing(tmp_path, monkeypatch):
    """os.mkdir used to fail when data/raw did not exist yet."""
    monkeypatch.setattr(paths, 'raw_data_path', tmp_path / 'nope' / 'raw')

    experiment = FrESHExperiment('202406190800_PAL20240619')

    assert experiment.pics_path.is_dir()


def test_a_full_path_is_accepted_as_the_name(raw_data_dir):
    """The metadata form used to pass an absolute path here."""
    experiment = FrESHExperiment(raw_data_dir / '202406190800_PAL20240619')

    assert experiment.exp_name == '202406190800_PAL20240619'
    assert experiment.experiment_path == raw_data_dir / '202406190800_PAL20240619'


def test_set_metadata_writes_metadata_json(raw_data_dir):
    experiment = FrESHExperiment('202406190800_PAL20240619')
    experiment.set_metadata(ExperimentMetadata(label='PAL20240619',
                                               experiment_type='Filter',
                                               station='PAL'))

    stored = json.loads((experiment.experiment_path / 'metadata.json').read_text())

    assert stored['label'] == 'PAL20240619'


def test_an_unknown_station_is_corrected_from_the_label(raw_data_dir):
    """The old code only corrected a hardcoded 'JFK' that no station ever uses."""
    experiment = FrESHExperiment('202406190800_PAL20240619')
    experiment.set_metadata(ExperimentMetadata(label='PAL20240619', station='JFK',
                                               experiment_type='Filter'))

    experiment.validate_and_correct_metadata()

    assert experiment.metadata.station == 'PAL'


@pytest.mark.parametrize('experiment_type, expected', [
    ('Filter', 2.0 * 0.01 / (1.0 * 5e-05)),
    ('filter', 2.0 * 0.01 / (1.0 * 5e-05)),   # matching is case insensitive
    ('Water background', 1.0),
    (None, 1.0),
    ('vaya uno a saber', 1.0),
])
def test_normalisation_factor(raw_data_dir, experiment_type, expected):
    experiment = FrESHExperiment('202406190800_PAL20240619')
    experiment.metadata = ExperimentMetadata(
        label='PAL20240619', experiment_type=experiment_type,
        v_drop=5e-05, v_wash=0.01, dil_factor=2.0, filter_fraction=1.0)

    experiment.calculate_normalisation_factor()

    assert experiment.metadata.normalisation_factor == pytest.approx(expected)


def test_normalisation_survives_missing_numbers(raw_data_dir):
    experiment = FrESHExperiment('202406190800_PAL20240619')
    experiment.metadata = ExperimentMetadata(label='PAL20240619',
                                             experiment_type='Filter',
                                             v_drop=None)

    experiment.calculate_normalisation_factor()

    assert experiment.metadata.normalisation_factor == 1.0
