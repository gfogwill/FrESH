import os
import json
import cv2

from datetime import datetime

import numpy as np
import yaml
import logging

from src import paths
from src.analysis import circles
from src.analysis.circles import auto_crop
from src.gui.experiment_gui import convert_cv_qt


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
        self.template_img = kwargs.get('template_img', 'template_image_2.png')
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

    def check_required_fields(self):
        """
        Checks whether the required fields are present in the metadata.

        Raises
        ------
        ValueError
            If one or more required fields are missing.
        """
        try:
            self.start_time = self.start_time.strftime('%Y-%m-%d %H:%M')
            self.end_time = self.end_time.strftime('%Y-%m-%d %H:%M')
        except AttributeError:
            pass

        required_fields = ["label"]
        missing_fields = [field for field in required_fields if getattr(self, field) is None]
        if missing_fields:
            raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")


class FrESHExperiment:
    def __init__(self, experiment_name):
        self.exp_name = experiment_name
        self.metadata = None

        self.is_analyzed = False

        experiment_path = paths.raw_data_path / experiment_name

        # create experiment directory if it doesn't exist
        if not os.path.exists(experiment_path):
            logging.info(f"Creating new experiment: {experiment_path}")
            os.mkdir(experiment_path)
            os.mkdir(experiment_path / 'pics')

        else:
            logging.info(f"Experiment found! Loading experiment: {experiment_path}")
            self.populate_image_list()
            self.load_metadata()

    def get_experiment_image_list(self):
        img_file_list = self.img_files
        if self.metadata.scan_start_timestamp is not None:
            filtered_img_files = [file for file in img_file_list if self.is_valid_timestamp(file)]
        else:
            filtered_img_files = img_file_list

        return filtered_img_files

    def is_valid_timestamp(self, file):
        # Extract timestamp from the filename
        timestamp_str = file.split(".")[0]  # Remove extension

        # Convert timestamp strings to datetime objects
        timestamp = datetime.strptime(timestamp_str, "%Y%m%d%H%M%S")
        start_timestamp = datetime.strptime(self.scan_start_timestamp, "%Y%m%d%H%M%S")
        end_timestamp = datetime.strptime(self.scan_end_timestamp, "%Y%m%d%H%M%S")

        return start_timestamp <= timestamp <= end_timestamp


    def run_analysis(self):
        img_file_list = self.get_experiment_image_list()

        self.grayscales_evolution = self.process_images(img_file_list)
        self.freezing_idxs = calculate_freezing_idxs(self.grayscales_evolution)

        self.del_indx = [i - 1 for i in self.metadata.del_index]
        self.freezing_idxs = np.delete(self.freezing_idxs, self.del_indx)
        freezing_times = calculate_freezing_times(img_file_list, self.freezing_idxs)

        self.freezing_temps = calculate_freezing_temps(freezing_times, self.exp_name)

        self.t, self.ff = process_sensors_data(self.exp_name, self.freezing_idxs, freezing_times)

        nu = self.metadata.dil_factor
        v_wash = self.metadata.v_wash
        v_drop = self.metadata.v_drop
        v_air = float(self.metadata.air_volume)
        filter_fraction = self.metadata.filter_fraction

        # Normalization factor to L^-1
        try:
            X = nu * v_wash / (v_air * filter_fraction)
        except TypeError:
            logging.warning("Error calculating normalization factor.")
            X = 1

        # Concentration per sample
        self.conc_per_drop = - np.log(1 - np.array(self.ff)) / v_drop

        # Concentration per standar L of air
        self.conc_per_L = self.conc_per_drop * X

        self.is_analyzed = True

    def process_images(self, img_files):
        # function to process the images and return the grayscales
        res = []

        self.detect_circles()

        for img_file in img_files:
            img_path = str(img_file)
            img = cv2.imread(img_path)
            rotation_option = self.metadata.rotation  # self.rotation_combobox.currentText()

            if rotation_option is not None:
                img = cv2.rotate(img, rotation_option)

            img = auto_crop(img, self.metadata.template_img)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            res.append(circles.get_grayscales(gray, self.circles_positions))

        return np.array(res)

    def get_img(self, frame_index, selected_droplet=None):

        if self.img_files is None or frame_index < 0 or frame_index >= len(self.img_files):
            return None

        img = cv2.imread(str(self.img_files[frame_index]))

        if self.metadata.rotation is not None:
            img = cv2.rotate(img, self.metadata.rotation)

        if self.metadata.template_img is not None:
            img = auto_crop(img, self.metadata.template_img)

        if hasattr(self, "circles_positions"):
            np_dcirc = np.uint16(np.around(self.circles_positions))

            for n, i in enumerate(np_dcirc):
                if selected_droplet is not None and selected_droplet == n:
                    circle_width = 2
                else:
                    circle_width = 1
                cv2.circle(img, (i[0], i[1]), i[2], (0, 0, 255), circle_width)
                cv2.putText(img, "{}".format(n), (i[0], i[1]), cv2.FONT_HERSHEY_PLAIN, 1.0, (255, 255, 0), 1)

        if hasattr(self, "freezing_idxs"):
            np_dcirc = np.uint16(np.around(self.circles_positions))

            for n, i in enumerate(np_dcirc):
                if self.freezing_idxs[n] > frame_index:
                    cv2.circle(img, (i[0], i[1]), i[2], (0, 0, 255), 1)
                    cv2.putText(img, "{}".format(n), (i[0], i[1]), cv2.FONT_HERSHEY_PLAIN, 1.0, (255, 255, 0), 1)
                else:
                    cv2.circle(img, (i[0], i[1]), i[2], (0, 255, 0), 1)
                    cv2.putText(img, "{}".format(n), (i[0], i[1]), cv2.FONT_HERSHEY_PLAIN, 1.0, (255, 255, 0), 1)

        return img

    def detect_circles(self):
        img = cv2.imread(str(self.img_files[0]))

        if self.metadata.rotation is not None:
            img = cv2.rotate(img, self.metadata.rotation)

        if self.metadata.template_img is not None:
            img = auto_crop(img, self.metadata.template_img)

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        self.circles_positions = circles.get_circles(gray, **self.metadata.hough_params, sort=True, plot=True)

    def populate_image_list(self):
        img_dir = paths.raw_data_path / self.exp_name / 'pics'

        # get a list of all JPG files in the directory
        self.img_files = [f for f in img_dir.iterdir() if f.is_file() and f.suffix == ".jpg"]
        # sort the list of images
        self.img_files.sort()

        if self.img_files.__len__() == 0:
            logging.error(f"No pictures found in dir: {img_dir}")

    def set_metadata(self, metadata):
        # implementation for collecting particles onto a membrane filter
        metadata.check_required_fields()
        self.metadata = metadata
        self.save_metadata_to_file()

    def save_metadata_to_file(self):
        # saves metadata to a JSON file
        self.metadata.check_required_fields()
        metadata_path = os.path.join(paths.raw_data_path / self.exp_name, f"metadata.json")
        with open(metadata_path, "w") as metadata_file:
            # Convert specific fields to float before saving
            metadata_dict = self.metadata.__dict__
            fields_to_convert_to_float = ["air_volume", "v_drop", "v_wash", "dil_factor", "filter_fraction"]
            for field in fields_to_convert_to_float:
                if field in metadata_dict and metadata_dict[field]:
                    metadata_dict[field] = float(metadata_dict[field])

            json.dump(metadata_dict, metadata_file, indent=4)

    def load_metadata(self):
        # loads metadata from a JSON file
        metadata_path = os.path.join(paths.raw_data_path / self.exp_name, f"metadata.json")
        if os.path.exists(metadata_path):
            with open(metadata_path, "r") as metadata_file:
                metadata_dict = json.load(metadata_file)
                metadata_dict = {k.lower(): v for k, v in metadata_dict.items()}
                self.metadata = ExperimentMetadata(**metadata_dict)
                return self.metadata
        else:
            return None

    def import_metadata(self, import_path):
        # loads metadata from a file
        with open(import_path, "r") as import_file:
            metadata_dict = json.load(import_file)
            self.metadata = ExperimentMetadata(**metadata_dict)
        self.save_metadata_to_file()

    def export_metadata(self, export_format="json"):
        # exports metadata to a file in the specified format (JSON or YAML)
        if export_format == "json":
            export_path = os.path.join(paths.raw_data_path / self.exp_name, f"metadata.json")
            with open(export_path, "w") as export_file:
                json.dump(self.metadata.__dict__, export_file, indent=4)
        elif export_format == "yaml":
            export_path = os.path.join(paths.raw_data_path / self.exp_name, f"metadata.yaml")
            with open(export_path, "w") as export_file:
                yaml.dump(self.metadata.__dict__, export_file, default_flow_style=False)
        else:
            print(f"Unsupported export format: {export_format}")


def process_sensors_data(exp_name, freezing_idxs, freezing_times):
    # function to process the sensors data and return the t and ff arrays
    str2date = lambda x: datetime.strptime(x.decode("utf-8"), '%Y-%m-%d %H:%M:%S')
    data = np.genfromtxt(paths.raw_data_path / exp_name / 'sensors_data.csv',
                         delimiter=',',
                         dtype=None,
                         names=True,
                         converters={0: str2date})

    t = []
    ff = []

    for i, line in enumerate(data):
        t.append(line[2])
        ff.append((freezing_times <= line['datetime']).sum() / freezing_idxs.__len__())

    return t, ff


def calculate_frame_temperatures(img_files, exp_name):
    # function to calculate temperatures which correspond to displayed images

    # image times
    times = [datetime.strptime(img_files[i].stem, "%Y%m%d%H%M%S") for i in range(len(img_files))]
    # corresponding temperatures
    str2date = lambda x: datetime.strptime(x.decode("utf-8"), '%Y-%m-%d %H:%M:%S')
    data = np.genfromtxt(paths.raw_data_path / exp_name / 'sensors_data.csv',
                         delimiter=',',
                         dtype=None,
                         names=True,
                         converters={0: str2date})
    t = []
    for time in times:
        matching_data = next((line[2] for line in data if line['datetime'] == time), None)
        if matching_data is None:
            # Find the nearest available temperature by finding the data point with the closest timestamp
            nearest_data = min(data, key=lambda line: abs(line['datetime'] - time))
            t.append(nearest_data[2])
        else:
            t.append(matching_data)

    return t


def calculate_freezing_idxs(grayscales_evolution):
    # function to calculate the freezing indices
    freezing_idxs = []
    for i in range(grayscales_evolution.shape[-1]):
        grayscales_diffs = [- s + t for s, t in zip(grayscales_evolution[:, i], grayscales_evolution[1:, i])]
        freezing_idxs.append(np.argmax(np.abs(grayscales_diffs)) + 1)
    return freezing_idxs


def calculate_freezing_times(img_files, freezing_idxs):
    # function to calculate the freezing times
    freezing_times = []
    for i, idx in enumerate(freezing_idxs):
        freezing_times.append(datetime.strptime(img_files[freezing_idxs[i]].stem, "%Y%m%d%H%M%S"))

    return np.array(freezing_times)


def calculate_freezing_temps(freezing_times, exp_name):
    str2date = lambda x: datetime.strptime(x.decode("utf-8"), '%Y-%m-%d %H:%M:%S')
    data = np.genfromtxt(paths.raw_data_path / exp_name / 'sensors_data.csv',
                         delimiter=',',
                         dtype=None,
                         names=True,
                         converters={0: str2date})
    t = []
    for index, time in enumerate(freezing_times):
        matching_data = next((line[2] for line in data if line['datetime'] == time), None)
        if matching_data is None:
            # Find the nearest available temperature by finding the data point with the closest timestamp
            nearest_data = min(data, key=lambda line: abs(line['datetime'] - time))
            t.extend([index, nearest_data[2]])
        else:
            t.extend([index, matching_data])

    return t
