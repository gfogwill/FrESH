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
                 station=None, label=None, sampler_id=None, sampler_status=None, air_volume=None, start_time=None,
                 end_time=None, flow=None, temp=None, press=None, exp_description=None, run=None, v_drop=None,
                 v_wash=None, dil_factor=None, filter_fraction=None, filter_position=None, chiller_model=None,
                 template_img='template_image_2.png', rotation=cv2.ROTATE_90_CLOCKWISE, hough_params=None,
                 del_index=[]):

        # Collection
        self.station = station
        self.storage_temperature = storage_temperature
        self.experiment_type = experiment_type
        self.label = label

        self.sampler_id = sampler_id
        self.sampler_status = sampler_status
        self.filter_position = filter_position
        self.air_volume = air_volume

        self.start_time = start_time
        self.end_time = end_time
        self.sampling_time = sampling_time
        self.sampling_interval = sampling_interval

        self.flow = flow
        self.temp = temp
        self.press = press

        self.exp_description = exp_description
        self.run = run

        self.template_img = template_img
        self.rotation = rotation

        self.v_drop = v_drop
        self.v_wash = v_wash
        self.dil_factor = dil_factor
        self.filter_fraction = filter_fraction

        self.chiller_model = chiller_model

        if hough_params is None:
            self.hough_params = {
                "min_distance": 24,
                "param1": 150,
                "param2": 15,
                "min_radius": 13,
                "max_radius": 15}
        else:
            self.hough_params = hough_params

        self.del_index = del_index

    def check_required_fields(self):
        """
        Checks whether the required fields are present in the metadata.

        Raises
        ------
        ValueError
            If one or more required fields are missing.
        """
        try:
            self.start_time = self.start_time.strftime('%Y-%m-%d %H:%M:%S')
            self.end_time = self.end_time.strftime('%Y-%m-%d %H:%M:%S')
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

    def run_analysis(self):
        nu = self.metadata.dil_factor
        v_wash = self.metadata.v_wash
        v_drop = self.metadata.v_drop
        v_air = float(self.metadata.air_volume)
        filter_fraction = self.metadata.filter_fraction

        self.grayscales_evolution = self.process_images(self.img_files)
        self.freezing_idxs = calculate_freezing_idxs(self.grayscales_evolution)

        self.del_indx = [i - 1 for i in self.metadata.del_index]
        self.freezing_idxs = np.delete(self.freezing_idxs, self.del_indx)
        freezing_times = calculate_freezing_times(self.img_files, self.freezing_idxs)

        self.freezing_temps = calculate_freezing_temps(freezing_times, self.exp_name)

        self.t, self.ff = process_sensors_data(self.exp_name, self.freezing_idxs, freezing_times)

        # self.FFwidget.clear()
        # self.FFwidget.plot(self.t, self.ff)

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

            if rotation_option != '-':
                img = cv2.rotate(img, rotation_option)

            img = auto_crop(img, self.metadata.template_img)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # dcirc = circles.get_circles(gray, minDist, param1, param2, minRadius, maxRadius, sort=True, plot=False)

            res.append(circles.get_grayscales(gray, self.circles_positions))

            # img = circles.add_circles(gray, self.circles_positions)

#            qt_img = convert_cv_qt(img)
#            self.image_frame.setPixmap(qt_img)

        return np.array(res)

    def get_img(self, frame_index):

        if self.img_files is None or frame_index < 0 or frame_index >= len(self.img_files):
            return None

        img = cv2.imread(str(self.img_files[frame_index]))

        if self.metadata.rotation is not None:
            img = cv2.rotate(img, self.metadata.rotation)

        if self.metadata.template_img is not None:
            img = auto_crop(img, self.metadata.template_img)

        if hasattr(self, "freezing_idxs"):
            np_dcirc = np.uint16(np.around(self.circles_positions))

            for n, i in enumerate(np_dcirc):
                if self.freezing_idxs[n] > frame_index:
                    cv2.circle(img, (i[0], i[1]), i[2], (0, 0, 255), 1)
                    cv2.putText(img, "{}".format(n), (i[0], i[1]), cv2.FONT_HERSHEY_PLAIN, 1.0, (255, 255, 0), 1)
                else:
                    cv2.circle(img, (i[0], i[1]), i[2], (0, 255, 0), 1)
                    cv2.putText(img, "{}".format(n), (i[0], i[1]), cv2.FONT_HERSHEY_PLAIN, 1.0, (255, 255, 0), 1)

        if hasattr(self, "circles_positions"):
            np_dcirc = np.uint16(np.around(self.circles_positions))

            for n, i in enumerate(np_dcirc):
                cv2.circle(img, (i[0], i[1]), i[2], (0, 0, 255), 1)
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
        self._save_metadata()

    def _save_metadata(self):
        # saves metadata to a JSON file
        metadata_path = os.path.join(paths.raw_data_path / self.exp_name, f"metadata.json")
        with open(metadata_path, "w") as metadata_file:
            json.dump(self.metadata.__dict__, metadata_file, indent=4)

    def save_metadata_to_file(self):
        # saves metadata to a JSON file
        self.metadata.check_required_fields()
        metadata_path = os.path.join(paths.raw_data_path / self.exp_name, f"metadata.json")
        with open(metadata_path, "w") as metadata_file:
            json.dump(self.metadata.__dict__, metadata_file, indent=4)

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
        self._save_metadata()

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
        grayscales_diffs = [s - t for s, t in zip(grayscales_evolution[:, i], grayscales_evolution[1:, i])]
        freezing_idxs.append(np.argmax(grayscales_diffs) + 1)
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
