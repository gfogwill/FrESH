"""The metadata form (src/gui/experiment_metadata.py)."""

import pytest

from src import paths
from src.experiment.metadata import ExperimentMetadata
from src.gui.experiment_metadata import ExperimentMetadataUi, fill_missing

UI_FILE = paths.src_module_dir / 'gui' / 'double_experiment_metadata.ui'

SAMPLER_CSV = (
    "No;Status;StartDate;StartTime;EndDate;EndTime;Dur;Pos;Volume;Flow;Temp;Press\n"
    "1;OK;19.06.2024;08:00;20.06.2024;08:00;24;7;21307.4;15.0;5.2;980.1\n"
    "2;OK;20.06.24;08:00;21.06.24;08:00;24;8;20111.2;15.0;4.8;979.0\n"
)


@pytest.fixture
def sampler_files(raw_data_dir, monkeypatch):
    """A sampler summary CSV for the Pallas station."""
    directory = paths.external_data_path / 'sampler_raw_data' / '36PALLAS'
    directory.mkdir(parents=True)
    (directory / 'SUM.CSV').write_text(SAMPLER_CSV, encoding='utf-8')
    return directory


@pytest.fixture
def form(qapp, sampler_files):
    return ExperimentMetadataUi(UI_FILE)


def fill(form, key, **fields):
    for name, value in fields.items():
        form._set_text(name, key, value)


def test_typed_values_survive_a_matching_sampler_record(form):
    """Regression: the form used to be thrown away whenever the label matched.

    Pressing OK replaced everything the operator had typed with the sampler
    CSV row, silently losing the description, dilution factor and wash volume.
    """
    fill(form, 'A', Label='PAL20240619', Description='muestra rara',
         DilFactor='2.5', VolWash='0.005')

    form._update_metadata_list()
    metadata = form.metadata_experiments[0]

    assert metadata.exp_description == 'muestra rara'
    assert metadata.dil_factor == 2.5
    assert metadata.v_wash == 0.005


def test_sampler_record_fills_the_empty_fields(form):
    """What the operator leaves blank still comes from the sampler files."""
    fill(form, 'A', Label='PAL20240619')

    form._update_metadata_list()
    metadata = form.metadata_experiments[0]

    assert metadata.air_volume == 21307.4
    assert metadata.start_time == '2024-06-19 08:00'
    assert metadata.end_time == '2024-06-20 08:00'
    assert metadata.filter_position == 7   # no widget for this one at all
    assert metadata.sampler_id == 'Z36'


def test_two_digit_years_are_understood(form):
    """The sampler writes both 19.06.2024 and 20.06.24."""
    fill(form, 'A', Label='PAL20240620')

    form._update_metadata_list()

    assert form.metadata_experiments[0].air_volume == 20111.2


def test_labels_are_upper_cased_and_the_station_comes_from_them(form):
    fill(form, 'A', Label='pal20240619')

    form._update_metadata_list()
    metadata = form.metadata_experiments[0]

    assert metadata.label == 'PAL20240619'
    assert metadata.station == 'PAL'


def test_invalid_numbers_do_not_crash_the_form(form):
    """A typo in a numeric field is ignored instead of raising ValueError."""
    fill(form, 'A', Label='HEL20240101', AirVolume='no es un numero')

    form._update_metadata_list()

    assert form.metadata_experiments[0].air_volume is None


def test_unknown_label_still_produces_metadata(form):
    """No sampler row: whatever is in the form is used as-is."""
    fill(form, 'A', Label='HEL20240101', AirVolume='1234.5', Description='a mano')

    form._update_metadata_list()
    metadata = form.metadata_experiments[0]

    assert metadata.air_volume == 1234.5
    assert metadata.exp_description == 'a mano'


def test_empty_form_yields_no_experiments(form):
    form._update_metadata_list()

    assert form.metadata_experiments == []


def test_fill_missing_never_overwrites_a_value():
    metadata = ExperimentMetadata(label='X', air_volume=1.0, temp=None)
    source = ExperimentMetadata(label='X', air_volume=999.0, temp=5.2)

    fill_missing(metadata, source)

    assert metadata.air_volume == 1.0
    assert metadata.temp == 5.2
