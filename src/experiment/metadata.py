"""The experiment metadata record.

Split out of ``experiment.py`` so that modules which only need the metadata
container (the sampler CSV reader, the GUI forms) do not have to import the
whole experiment/analysis machinery.
"""

import cv2

# Experiment types, exactly as spelled in the combo boxes of the .ui files.
# Kept here so the GUI and the normalisation code agree on the spelling.
TYPE_FILTER = 'Filter'
TYPE_FILTER_BACKGROUND = 'Filter background'
TYPE_FIELD_BACKGROUND = 'Field background'
TYPE_PUNCHED_FILTER = 'Punched filter'
TYPE_PUNCHED_FILTER_BACKGROUND = 'Punched filter background'
TYPE_WATER_BACKGROUND = 'Water background'

# --- normalisation ---------------------------------------------------------
# Which experiment types get which normalisation factor. These sets reproduce
# exactly what the code did before, so no already-analysed experiment changes
# its numbers.
#
# NOTE: the old code listed 'filter Background' in the wash branch but compared
# it against an already-lower-cased string, so that entry could never match, and
# it had a 'WB' branch that no combo box ever emits. 'Filter background',
# 'Field background' and 'Water background' therefore all fall through to
# X = 1.0, which is left as it was.
#
# That is on purpose: per the lab, the background types are not normalised per
# litre of air at all -- they are expressed per mL of suspension. Getting that
# right means more than adding them to a set here: run_analysis() also divides
# by air_volume and labels the result L-1 for every type. Until somebody
# confirms the intended formula, nothing here is changed, because touching it
# would silently move the numbers of every background already analysed.

# Types normalised with the filter-wash formula X = nu * v_wash / (ff * v_drop).
WASH_NORMALISED_TYPES = (TYPE_FILTER,)
# Types normalised from the punch-out / filter area ratio.
AREA_NORMALISED_TYPES = (TYPE_PUNCHED_FILTER, TYPE_PUNCHED_FILTER_BACKGROUND)

# Backwards-compatible aliases.
FILTER_TYPES = WASH_NORMALISED_TYPES
PUNCHED_TYPES = AREA_NORMALISED_TYPES


class ExperimentMetadata:
    def __init__(self, **kwargs):
        # Default values for metadata fields
        self.sampling_time = kwargs.get('sampling_time', None)
        self.sampling_interval = kwargs.get('sampling_interval', 10)
        self.storage_temperature = kwargs.get('storage_temperature', -20)
        self.experiment_type = kwargs.get('experiment_type', None)
        self.station = kwargs.get('station', None)
        self.label = kwargs.get('label', None)
        self.sampler_id = kwargs.get('sampler_id', None)
        self.sampler_status = kwargs.get('sampler_status', None)
        self.air_volume = kwargs.get('air_volume', None)
        self.start_time = kwargs.get('start_time', None)
        self.end_time = kwargs.get('end_time', None)
        self.flow = kwargs.get('flow', None)
        self.temp = kwargs.get('temp', None)
        self.press = kwargs.get('press', None)
        self.exp_description = kwargs.get('exp_description', None)
        self.run = kwargs.get('run', None)
        self.template_img = kwargs.get('template_img', 'template_image.png')
        self.rotation = kwargs.get('rotation', cv2.ROTATE_90_CLOCKWISE)
        self.hough_params = kwargs.get('hough_params', {
            "min_distance": 24,
            "param1": 150,
            "param2": 15,
            "min_radius": 13,
            "max_radius": 15
        })
        self.del_index = kwargs.get('del_index', [])
        self.scan_start_timestamp = kwargs.get('scan_start_timestamp', None)
        self.scan_end_timestamp = kwargs.get('scan_end_timestamp', None)
        self.v_drop = kwargs.get('v_drop', None)
        self.v_wash = kwargs.get('v_wash', None)
        self.dil_factor = kwargs.get('dil_factor', None)
        self.filter_fraction = kwargs.get('filter_fraction', None)
        self.filter_position = kwargs.get('filter_position', None)
        self.chiller_model = kwargs.get('chiller_model', None)

        # adding the background experiment
        self.background_exp = kwargs.get('background_exp', None)
        # punchout metadata
        self.filter_diameter = kwargs.get('filter_diameter', None)
        self.puncher_diameter = kwargs.get('puncher_diameter', None)
        self.filter_type = kwargs.get('filter_type', None)
        self.latitude = kwargs.get('latitude', None)
        self.longitude = kwargs.get('longitude', None)
        # adding info on the normalisation factor and resulting units
        self.normalisation_factor = kwargs.get('normalisation_factor', None)
        self.units = kwargs.get('units', 'L-1')


    def check_required_fields(self):
        """
        Checks whether the required fields are present in the metadata.

        Raises
        ------
        ValueError
            If one or more required fields are missing.
        """
        # One try block covered both, so a missing start_time skipped the
        # conversion of end_time and left a datetime in the metadata, which
        # json.dump cannot serialise.
        for field in ('start_time', 'end_time'):
            value = getattr(self, field)
            if hasattr(value, 'strftime'):
                setattr(self, field, value.strftime('%Y-%m-%d %H:%M'))

        required_fields = ["label"]
        missing_fields = [field for field in required_fields if getattr(self, field) is None]
        if missing_fields:
            raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")
