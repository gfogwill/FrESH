import os
import json
import yaml
import logging

from src import paths


class ExperimentMetadata:
    """
    Represents metadata for a FrESH experiment.

    Attributes
    ----------
    station : str
        The station where the sample was collected.
    sampling_time : str
        The sampling time for the experiment.
    sampling_interval : int
        The sampling interval for the experiment.
    storage_temperature : int
        The storage temperature for the experiment.
    experiment_type : str
        The type of the experiment .
    label : str, optional
        The label for the sample.
    sampler_ID : str, optional
        The ID of the sampler.
    air_volume : str, optional
        The volume of air sampled (if applicable).
    start_time : str, optional
        The start time of the experiment.
    end_time : str, optional
        The end time of the experiment.
    temp : str, optional
        The temperature during the experiment.
    press : str, optional
        The pressure during the experiment.
    exp_description : str, optional
        A description of the experiment.
    run : str, optional
        The run number for the experiment.
    """

    def __init__(self, sampling_time=None, sampling_interval=10, storage_temperature=-20, experiment_type=None,
                 station=None, label=None, sampler_ID=None, air_volume=None, start_time=None, end_time=None, temp=None,
                 press=None, exp_description=None, run=None, v_drop=None, v_wash=None,
                 dil_factor=None, filter_fraction=None):
        self.station = station
        self.sampling_time = sampling_time
        self.sampling_interval = sampling_interval
        self.storage_temperature = storage_temperature
        self.experiment_type = experiment_type
        self.label = label
        self.sampler_ID = sampler_ID
        self.air_volume = air_volume
        self.start_time = start_time
        self.end_time = end_time
        self.temp = temp
        self.press = press
        self.exp_description = exp_description
        self.run = run
        self.v_drop = v_drop
        self.v_wash = v_wash
        self.dil_factor = dil_factor
        self.filter_fraction = filter_fraction

    def check_required_fields(self):
        """
        Checks whether the required fields are present in the metadata.

        Raises
        ------
        ValueError
            If one or more required fields are missing.
        """
        required_fields = ["experiment_type"]
        missing_fields = [field for field in required_fields if getattr(self, field) is None]
        if missing_fields:
            raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")


class FrESHExperiment:
    def __init__(self, experiment_name):
        self.experiment_name = experiment_name

        self.experiment_path = paths.raw_data_path / experiment_name

        # create experiment directory if it doesn't exist
        if not os.path.exists(self.experiment_path):
            logging.info(f"Creating new experiment: {self.experiment_path}")
            os.mkdir(self.experiment_path)
            os.mkdir(self.experiment_path / 'pics')

        else:
            self.load_metadata()

    def set_metadata(self, metadata):
        # implementation for collecting particles onto a membrane filter
        metadata.check_required_fields()
        self.metadata = metadata
        self._save_metadata()

    def _save_metadata(self):
        # saves metadata to a JSON file
        metadata_path = os.path.join(self.experiment_path, f"metadata.json")
        with open(metadata_path, "w") as metadata_file:
            json.dump(self.metadata.__dict__, metadata_file, indent=4)

    def load_metadata(self):
        # loads metadata from a JSON file
        metadata_path = os.path.join(self.experiment_path, f"metadata.json")
        if os.path.exists(metadata_path):
            with open(metadata_path, "r") as metadata_file:
                metadata_dict = json.load(metadata_file)
                self.metadata = ExperimentMetadata(**metadata_dict)
                return self.metadata
        else:
            return None

    def import_metadata(self, import_path):
        # loads metadata from a file
        with open(import_path, "r") as import_file:
            metadata_dict = json.load(import_file)
            self.metadata = ExperimentMetadata(**metadata_dict)
        self._save_metadata()

    def export_metadata(self, export_format="json"):
        # exports metadata to a file in the specified format (JSON or YAML)
        if export_format == "json":
            export_path = os.path.join(self.experiment_path, f"metadata.json")
            with open(export_path, "w") as export_file:
                json.dump(self.metadata.__dict__, export_file, indent=4)
        elif export_format == "yaml":
            export_path = os.path.join(self.experiment_path, f"metadata.yaml")
            with open(export_path, "w") as export_file:
                yaml.dump(self.metadata.__dict__, export_file, default_flow_style=False)
        else:
            print(f"Unsupported export format: {export_format}")

