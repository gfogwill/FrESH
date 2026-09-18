import logging

from PyQt6 import QtWidgets, uic

from src.config import get_chiller_model
from src.experiment import sampler_data
from src.experiment.metadata import ExperimentMetadata
from src.gui.experiment_gui import ExperimentUi
from src.stations import STATIONS, station_code

# Kept as an alias: older code imported this name from here.
stations_dict = STATIONS

# The per-experiment form fields, by the suffix of their widget name.
FORM_FIELDS = ('Label', 'SamplerID', 'AirVolume', 'StartTime', 'EndTime', 'Temp',
               'Press', 'Description', 'VolWash', 'DilFactor', 'FilterFraction')

# Which fields each sample type enables. Anything not listed is disabled.
ENABLED_FIELDS_BY_TYPE = {
    'Filter': {'SamplerID', 'AirVolume', 'StartTime', 'EndTime', 'Temp', 'Press',
               'DilFactor', 'FilterFraction'},
    'Field background': {'SamplerID', 'StartTime', 'EndTime', 'DilFactor', 'FilterFraction'},
    'Water background': set(),
}

# Metadata attributes that may be taken from the sampler CSV when the operator
# left the corresponding form field empty, plus the ones the form has no widget
# for at all.
SAMPLER_FILLABLE = ('sampler_id', 'sampler_status', 'air_volume', 'start_time',
                    'end_time', 'flow', 'temp', 'press', 'filter_position')


def _to_float(text, field_name=None):
    """Parse a form field into a float, returning None when it is empty/invalid."""
    text = (text or '').strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        logging.warning(f"Ignoring invalid number in field {field_name or '?'}: {text!r}")
        return None


def _is_empty(value):
    return value is None or (isinstance(value, str) and not value.strip())


def fill_missing(metadata, source, attributes=SAMPLER_FILLABLE):
    """Copy ``attributes`` from ``source`` into ``metadata`` where it has no value.

    The form is the source of truth: whatever the operator typed wins, and the
    sampler record is only used to fill the gaps.
    """
    for attribute in attributes:
        if _is_empty(getattr(metadata, attribute, None)):
            value = getattr(source, attribute, None)
            if not _is_empty(value):
                setattr(metadata, attribute, value)
    return metadata


class ExperimentMetadataUi(QtWidgets.QMainWindow):
    """The form where the operator describes the plate(s) before a scan."""

    def __init__(self, ui_file, *args, **kwargs):
        super(ExperimentMetadataUi, self).__init__(*args, **kwargs)

        uic.loadUi(ui_file, self)

        self.metadata_experiments = []
        self.ExperimentUi = None

        self.experiment_type_comboboxA = self.findChild(QtWidgets.QComboBox, 'comboBoxSampleType_A')
        self.experiment_type_comboboxA.currentTextChanged.connect(lambda: self.update_experiment_type('A'))

        self.experiment_type_comboboxB = self.findChild(QtWidgets.QComboBox, 'comboBoxSampleType_B')
        if self.experiment_type_comboboxB is not None:
            self.experiment_type_comboboxB.currentTextChanged.connect(lambda: self.update_experiment_type('B'))

        # Connect the button signals to their respective slots
        self.button_confirm = self.findChild(QtWidgets.QDialogButtonBox, 'ConfirmbuttonBox')
        self.button_confirm.accepted.connect(self.start_experiment)

        self.button_search_A = self.findChild(QtWidgets.QToolButton, 'searchByLabel_A')
        self.button_search_A.clicked.connect(lambda: self.search_experiment_metadata('A'))

        self.button_search_B = self.findChild(QtWidgets.QToolButton, 'searchByLabel_B')
        if self.button_search_B is not None:
            self.button_search_B.clicked.connect(lambda: self.search_experiment_metadata('B'))

    # -- widget helpers ------------------------------------------------------

    def _field(self, name, experiment_key):
        """Return the QPlainTextEdit for e.g. ('AirVolume', 'A')."""
        return self.findChild(QtWidgets.QPlainTextEdit, f'text{name}_{experiment_key}')

    def _text(self, name, experiment_key):
        widget = self._field(name, experiment_key)
        return widget.toPlainText().strip() if widget is not None else ''

    def _set_text(self, name, experiment_key, value):
        widget = self._field(name, experiment_key)
        if widget is not None:
            widget.setPlainText('' if value is None else str(value))

    def experiment_type(self, experiment_key):
        combobox = self.findChild(QtWidgets.QComboBox, f'comboBoxSampleType_{experiment_key}')
        return combobox.currentText() if combobox is not None else ''

    # -- form behaviour ------------------------------------------------------

    def update_experiment_type(self, experiment_key):
        """Enable only the fields that make sense for the selected sample type."""
        enabled = ENABLED_FIELDS_BY_TYPE.get(self.experiment_type(experiment_key))
        if enabled is None:
            return

        for name in FORM_FIELDS:
            if name in ('Label', 'Description', 'VolWash'):
                continue  # always available
            widget = self._field(name, experiment_key)
            if widget is not None:
                widget.setEnabled(name in enabled)

    def search_experiment_metadata(self, experiment_key):
        """Fill the form from the sampler's raw CSV files, using the label."""
        label = self._text('Label', experiment_key).upper()
        metadata = sampler_data.retrieve_metadata(label, self.experiment_type(experiment_key))

        if metadata is None:
            logging.warning(f"No sampler data found for {label}; fill the form by hand.")
            return

        self._populate_metadata_fields(metadata, experiment_key)

    def _populate_metadata_fields(self, metadata, experiment_key):
        self._set_text('Label', experiment_key, metadata.label)
        self._set_text('SamplerID', experiment_key, metadata.sampler_id)
        self._set_text('AirVolume', experiment_key, metadata.air_volume)
        self._set_text('StartTime', experiment_key, metadata.start_time)
        self._set_text('EndTime', experiment_key, metadata.end_time)
        self._set_text('Temp', experiment_key, metadata.temp)
        self._set_text('Press', experiment_key, metadata.press)
        self._set_text('Description', experiment_key, metadata.exp_description)
        self._set_text('VolWash', experiment_key, metadata.v_wash)
        self._set_text('DilFactor', experiment_key, metadata.dil_factor)
        self._set_text('FilterFraction', experiment_key, metadata.filter_fraction)

    # -- building the metadata ----------------------------------------------

    def _get_metadata_from_form(self, experiment_key):
        """Build an ExperimentMetadata out of what is currently in the form."""
        label = self._text('Label', experiment_key).upper()

        try:
            chiller_model = get_chiller_model()
        except Exception as e:
            logging.error(f"Could not read the chiller model from the configuration: {e}")
            chiller_model = None

        return ExperimentMetadata(
            station=station_code(label) or label[0:3],
            experiment_type=self.experiment_type(experiment_key),
            label=label,
            sampler_id=self._text('SamplerID', experiment_key) or None,
            start_time=self._text('StartTime', experiment_key) or None,
            end_time=self._text('EndTime', experiment_key) or None,
            air_volume=_to_float(self._text('AirVolume', experiment_key), 'air volume'),
            temp=_to_float(self._text('Temp', experiment_key), 'temperature'),
            press=_to_float(self._text('Press', experiment_key), 'pressure'),
            exp_description=self._text('Description', experiment_key) or None,
            v_wash=_to_float(self._text('VolWash', experiment_key), 'wash volume'),
            dil_factor=_to_float(self._text('DilFactor', experiment_key), 'dilution factor'),
            filter_fraction=_to_float(self._text('FilterFraction', experiment_key), 'filter fraction'),
            v_drop=5e-05,
            chiller_model=chiller_model,
        )

    def _collect_metadata(self, experiment_key):
        """Metadata for one plate: the form wins, the sampler CSV fills the gaps.

        The form used to be discarded entirely whenever the label matched a row
        in the sampler files, which silently threw away the description,
        dilution factor, wash volume and sample type the operator had typed.
        """
        metadata = self._get_metadata_from_form(experiment_key)

        record = sampler_data.retrieve_metadata(metadata.label, metadata.experiment_type)
        if record is not None:
            fill_missing(metadata, record)

        return metadata

    def _update_metadata_list(self):
        self.metadata_experiments.clear()

        keys = ['A']
        if self.button_search_B is not None:
            keys.append('B')

        for key in keys:
            if self._text('Label', key):
                self.metadata_experiments.append(self._collect_metadata(key))

    # -- confirming ----------------------------------------------------------

    def _warn(self, message):
        logging.warning(message)
        QtWidgets.QMessageBox.warning(self, "FrESH", message)

    def start_experiment(self):
        self._update_metadata_list()

        if not self.metadata_experiments:
            self._warn("No label given -- fill in at least one label before starting.")
            return

        try:
            for metadata in self.metadata_experiments:
                metadata.check_required_fields()
        except ValueError as e:
            self._warn(str(e))
            return

        labels = [metadata.label for metadata in self.metadata_experiments]
        if len(set(labels)) != len(labels):
            self._warn("Labels are the same!\nRename and try again.")
            return

        self.hide()
        # The scan window creates the experiment folders itself: with a
        # freeze/thaw series there is one per cycle, not one per run.
        self.ExperimentUi = ExperimentUi(self.metadata_experiments)
        self.ExperimentUi.show()
