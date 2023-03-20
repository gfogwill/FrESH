import os
import json
import yaml


class ExperimentMetadata:
    def __init__(self, sampling_time=None, sampling_interval=10, storage_temperature=-20, experiment_type=None):
        self.sampling_time = sampling_time
        self.sampling_interval = sampling_interval
        self.storage_temperature = storage_temperature
        self.experiment_type = experiment_type

    def check_required_fields(self):
        required_fields = ['sampling_time', 'experiment_type']
        missing_fields = [field for field in required_fields if getattr(self, field) is None]
        if missing_fields:
            raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")


class FrESHExperiment:
    def __init__(self, experiment_name):
        self.experiment_name = experiment_name
        self.experiment_dir = os.path.join(os.getcwd(), 'experiment', experiment_name)

        # create experiment directory if it doesn't exist
        if not os.path.exists(self.experiment_dir):
            os.makedirs(self.experiment_dir)

    def set_metadata(self, metadata):
        # implementation for collecting particles onto a membrane filter
        metadata.check_required_fields()
        self.metadata = metadata
        self._save_metadata()

    def _save_metadata(self):
        # saves metadata to a JSON file
        metadata_path = os.path.join(self.experiment_dir, f"{self.experiment_name}_metadata.json")
        with open(metadata_path, "w") as metadata_file:
            json.dump(self.metadata.__dict__, metadata_file)

    def load_metadata(self):
        # loads metadata from a JSON file
        metadata_path = os.path.join(self.experiment_dir, f"{self.experiment_name}_metadata.json")
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
            export_path = os.path.join(self.experiment_dir, f"{self.experiment_name}_metadata.json")
            with open(export_path, "w") as export_file:
                json.dump(self.metadata.__dict__, export_file)
        elif export_format == "yaml":
            export_path = os.path.join(self.experiment_dir, f"{self.experiment_name}_metadata.yaml")
            with open(export_path, "w") as export_file:
                yaml.dump(self.metadata.__dict__, export_file, default_flow_style=False)
        else:
            print(f"Unsupported export format: {export_format}")

