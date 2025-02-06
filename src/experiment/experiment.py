import os
import json
import cv2

from datetime import datetime
from itertools import takewhile

import numpy as np
import yaml
import logging

from src import paths
from src.analysis import circles
from src.analysis.circles import auto_crop
from src.gui.experiment_gui import convert_cv_qt
from src.experiment.data_analysis import spectra

stations_dict = {
    'WBG': {
        'station_name': 'Water backgroung',
        'station_mapping': None,
        'sampler_id': None,
        'latitude': 0.0,
        'longitude': 0.0,
        'altitude': 0.0
    },
    'HEL': {
        'station_name': 'Helsinki',
        'station_mapping': '01HELSINKI',
        'sampler_id': 'Z01',
        'latitude': 60.1699,
        'longitude': 24.9384,
        'altitude': 17.0
    },
    'UTO': {
        'station_name': 'Utö',
        'station_mapping': '09UTÖ',
        'sampler_id': 'Z09',
        'latitude': 59.7763,
        'longitude': 21.4231,
        'altitude': 9.0
    },
    'KUO': {
        'station_name': 'Kuopio',
        'station_mapping': '77KUOPIO',
        'sampler_id': 'Z77',
        'latitude': 62.8926,
        'longitude': 27.6770,
        'altitude': 75.0
    },
    'PAL': {
        'station_name': 'Pallas',
        'station_mapping': '36PALLAS',
        'sampler_id': 'Z36',
        'latitude': 67.9674,
        'longitude': 24.1196,
        'altitude': 560.0
    },
    'VKK': {
        'station_name': 'Vikki',
        'station_mapping': 'Vikki',
        'sampler_id': 'Z01',
        'latitude': 1.0,
        'longitude': 1.0,
        'altitude': 0.0
    },
    'ODE': {
        'station_name': 'ODEN',
        'station_mapping': 'ODEN',
        'sampler_id': 'None',
        'latitude': 1.0,
        'longitude': 1.0,
        'altitude': 0.0
    },
    'NYA': {
        'station_name': 'Ny Ålesund',
        'station_mapping': 'NYÅLESUND',
        'sampler_id': 'None',
        'latitude': 78.9067,
        'longitude': 11.8883,
        'altitude': 474.0
    }
}


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

        # adding the background experiment
        self.background_exp = kwargs.get('background_exp', None)
        # punchout metadata
        self.filter_diameter = kwargs.get('filter_diameter', None)
        self.puncher_diameter = kwargs.get('puncher_diameter', None)
        self.filter_type = kwargs.get('filter_type', None)
        self.latitude = kwargs.get('latitude', None)
        self.longitude = kwargs.get('longitude', None)
        # adding info on the normalisation factor and resulting units
        self.normalisation_factor = kwargs.get('normalisation factor', None)
        self.units = kwargs.get('units', 'L-1')


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


def is_valid_date_format(date_str):
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def is_valid_sampled_vol(sampled_vol):
    try:
        sampled_vol_float = float(sampled_vol)
        return sampled_vol_float != 1
    except (ValueError, TypeError):
        return False


class FrESHExperiment:
    def __init__(self, experiment_name):
        self.exp_name = experiment_name
        self.metadata = None

        self.is_analyzed = False
        self.background_corrected = False
        self.already_reloaded = False  # Flag to prevent infinite loop
        self.t = []
        experiment_path = paths.raw_data_path / experiment_name

        # create experiment directory if it doesn't exist
        if not os.path.exists(experiment_path):
            logging.info(f"Creating new experiment: {experiment_path}")
            os.mkdir(experiment_path)
            os.mkdir(experiment_path / 'pics')

        else:
            logging.info(f"Experiment found! Loading experiment: {experiment_path}")
            self.load_metadata()
            self.img_files = self.get_experiment_image_list()

    def get_experiment_image_list(self):
        img_dir = paths.raw_data_path / self.exp_name / 'pics'
        # get a list of all JPG files in the directory
        img_file_list = [f for f in img_dir.iterdir() if f.is_file() and f.suffix == ".jpg" or f.suffix == ".png"]
        # sort the list of images
        img_file_list.sort()

        if img_file_list.__len__() == 0:
            logging.error(f"No pictures found in dir: {img_dir}")

        # Return the complete list if start_timestamp or end_timestamp are not defined
        if not (hasattr(self.metadata, 'scan_start_timestamp') and hasattr(self.metadata, 'scan_end_timestamp')):
            return img_file_list

        if self.metadata.scan_start_timestamp is not None:
            # Filter out images before start_timestamp
            start_timestamp = datetime.strptime(self.metadata.scan_start_timestamp, "%Y%m%d%H%M%S")
            img_file_list = [file for file in img_file_list if self.is_valid_timestamp(file, start_timestamp, None)]

        if self.metadata.scan_end_timestamp is not None:
            # Filter out images after end_timestamp
            end_timestamp = datetime.strptime(self.metadata.scan_end_timestamp, "%Y%m%d%H%M%S")
            img_file_list = [file for file in img_file_list if self.is_valid_timestamp(file, None, end_timestamp)]


        return img_file_list

    def is_valid_timestamp(self, file, start_timestamp, end_timestamp):
        # Extract timestamp from the filename
        timestamp_str = file.stem  # Remove extension

        # Convert timestamp strings to datetime objects
        timestamp = datetime.strptime(timestamp_str, "%Y%m%d%H%M%S")

        if start_timestamp is not None and end_timestamp is not None:
            return start_timestamp <= timestamp <= end_timestamp
        elif start_timestamp is not None:
            return start_timestamp <= timestamp
        elif end_timestamp is not None:
            return timestamp <= end_timestamp
        else:
            return True

    def run_analysis(self, existing_freezing_idxs=None):

        #self.metadata.scan_start_timestamp = None
        #self.metadata.scan_end_timestamp = None

        img_file_list = self.get_experiment_image_list()
        #print('\n image list', len(img_file_list), '\n')

        self.grayscales_evolution = self.process_images(img_file_list)
        #print('\n image list', len(self.greyscales_evolution), '\n')

        if existing_freezing_idxs is None:
            self.freezing_idxs = calculate_freezing_idxs(self.grayscales_evolution)

            self.del_indx = [i - 1 for i in self.metadata.del_index]
            self.freezing_idxs = np.delete(self.freezing_idxs, self.del_indx)

        else:
            self.freezing_idxs = existing_freezing_idxs


        freezing_times = calculate_freezing_times(img_file_list, self.freezing_idxs)

        self.freezing_temps = calculate_freezing_temps(freezing_times, self.exp_name)

        self.t, self.ff = process_sensors_data(self.exp_name, self.freezing_idxs, freezing_times)

        background_experiment_save = self.metadata.background_exp
        if background_experiment_save!= 'None' and background_experiment_save is not None:
            bg_metadata = self.load_background_metadata(background_experiment_save)
            X_bg = bg_metadata.normalisation_factor
        else:
            X_bg = 1.0

        # X is normalisation applied before bg correction, sampled volume correction is applied after

        self.calculate_normalisation_factor()
        X = self.metadata.normalisation_factor
        v_air = np.float64(self.metadata.air_volume)

        # Concentration per sample
        self.conc_per_drop = - np.log(1 - np.array(self.ff)) * X # / v_drop is already calculated

        # Concentration per standar L of air
        self.conc_per_L = self.conc_per_drop / v_air

        self.spectra, self.background_corrected = spectra(self.freezing_temps, X, v_air, 0.5, 1.96,
                                                          background_exp=background_experiment_save,
                                                          X_bg=np.float64(X_bg), depression=0)

        self.is_analyzed = True

    def calculate_normalisation_factor(self):
        v_drop = self.metadata.v_drop
        if self.metadata.experiment_type in ['Filter', 'Filter Background']:
            nu = self.metadata.dil_factor
            v_wash = self.metadata.v_wash
            #v_air = self.metadata.air_volume # float(self.metadata.air_volume) # NOTE: afte bg correction!
            filter_fraction = float(self.metadata.filter_fraction)
            # Normalization factor to L^-1
            try:
                X = nu * v_wash / (filter_fraction * v_drop)
            except TypeError:
                logging.warning("Error calculating normalization factor.")
                X = 1
        elif self.metadata.experiment_type in ['Punched filter', 'Punched filter background']:
            try:
                d_filter = self.metadata.filter_diameter # 0.135 m
                d_punchout = self.metadata.puncher_diameter # 0.001  m
                filter_fraction = (0.5*d_filter)**2 / (0.5*d_punchout)**2
                #X = v_air * filter_fraction
                X = 1 / filter_fraction
            except TypeError:
                logging.warning("Error calculating normalization factor.")
                X = 1

        elif self.metadata.experiment_type == 'WB':
            X = v_drop
        else:
            print('Normalisation factro is set to 1.0')
            X = 1.0

        self.metadata.normalisation_factor = X



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

            #img = auto_crop(img, self.metadata.template_img)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            res.append(circles.get_grayscales(gray, self.circles_positions))

        return np.array(res)

    def detect_circles(self):
        img = cv2.imread(str(self.img_files[0]))

        if self.metadata.rotation is not None:
            img = cv2.rotate(img, self.metadata.rotation)

        if self.metadata.template_img is not None:
            pass
            #img = auto_crop(img, self.metadata.template_img)

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        self.circles_positions = circles.get_circles(gray, **self.metadata.hough_params, sort=True, plot=True)

    def get_img(self, frame_index, selected_droplet=None):

        if self.img_files is None or frame_index < 0 or frame_index >= len(self.img_files):
            return None

        img = cv2.imread(str(self.img_files[frame_index]))

        if self.metadata.rotation is not None:
            img = cv2.rotate(img, self.metadata.rotation)

        if self.metadata.template_img is not None:
            #img = auto_crop(img, self.metadata.template_img)
            pass

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

    def get_processed_data(self):
        return np.genfromtxt(os.path.join(paths.processed_data_path, self.exp_name, 'report.csv'),
                             delimiter=',',
                             dtype=None,
                             names=True)

    def set_metadata(self, metadata):
        # implementation for collecting particles onto a membrane filter
        metadata.check_required_fields()
        self.metadata = metadata
        self.save_metadata_to_file()

    def save_metadata_to_file(self):
        # saves metadata to a JSON file
        #self.metadata.scan_start_timestamp = None
        #self.metadata.scan_end_timestamp = None
        self.metadata.check_required_fields()
        metadata_path = os.path.join(paths.raw_data_path / self.exp_name, f"metadata.json")
        with open(metadata_path, "w") as metadata_file:
            # Convert specific fields to float before saving
            metadata_dict = self.metadata.__dict__
            fields_to_convert_to_float = ["air_volume", "v_drop", "v_wash", "dil_factor", "filter_fraction",
            				 "filter_diameter", "puncher_diameter", "normalisation_factor"]
            for field in fields_to_convert_to_float:
                if field in metadata_dict and metadata_dict[field]:
                    try:
                        metadata_dict[field] = float(metadata_dict[field])
                    except(ValueError):
                        metadata_dict[field] = 1.0
            print('\n Check metadata to be saved to a file', metadata_dict, '\n')
            json.dump(metadata_dict, metadata_file, indent=4)

    def load_metadata(self):
        metadata_path = os.path.join(paths.raw_data_path, self.exp_name, "metadata.json")
        if os.path.exists(metadata_path):
            if os.path.getsize(metadata_path) == 0:  # Check if file is empty
                print('file empty')
                self.load_metadata_from_raw_file(self.exp_name)
                return

            with open(metadata_path, "r", encoding="utf-8-sig") as metadata_file:
                try:
                    content = metadata_file.read()
                    content = content.replace('"None"', 'null')
                    content = content.replace('""', 'null')
                    #print('Check metadata to be loaded', content)
                    metadata_dict = json.loads(content)
                except json.JSONDecodeError as e:
                    print('Error loading metadata ', e)
                    #self.load_metadata_from_raw_file()
                    return

                metadata_dict = {k.lower(): v for k, v in metadata_dict.items()}
                self.metadata = ExperimentMetadata(**metadata_dict)

                # Validate and correct metadata fields
                self.validate_and_correct_metadata()

                return self.metadata
        else:
            return None

    def load_background_metadata(self, exp_name):
        metadata_path = os.path.join(paths.raw_data_path, exp_name, "metadata.json")
        if os.path.exists(metadata_path):
            if os.path.getsize(metadata_path) == 0:  # Check if file is empty
                print('file empty')
                self.load_metadata_from_raw_file(self.exp_name)
                return

            with open(metadata_path, "r", encoding="utf-8-sig") as metadata_file:
                try:
                    content = metadata_file.read()
                    content = content.replace('"None"', 'null')
                    content = content.replace('""', 'null')
                    metadata_dict = json.loads(content)
                except json.JSONDecodeError as e:
                    print('Error loading metadata ', e)
                    #self.load_metadata_from_raw_file()
                    return

                metadata_dict = {k.lower(): v for k, v in metadata_dict.items()}
                self.metadata = ExperimentMetadata(**metadata_dict)

                # Validate and correct metadata fields
                self.validate_and_correct_metadata()
                return self.metadata
        else:
            return None

    def validate_and_correct_metadata(self):
        needs_reload = False

        # Check and correct dil_factor
        if isinstance(self.metadata.dil_factor, int) and self.metadata.dil_factor == 1 or self.metadata.dil_factor is None:
            self.metadata.dil_factor = 1.0

        # Check and correct filter_fraction
        if isinstance(self.metadata.filter_fraction, int) and self.metadata.filter_fraction == 1 or self.metadata.filter_fraction is None:
            self.metadata.filter_fraction = 1.0

        if self.metadata.air_volume is None:
            #needs_reload = True
            self.metadata.air_volume = 1.0

        if self.metadata.background_exp is None:
            self.metadata.background_exp = 'None'

        # Validate start_time format
        if not self.is_valid_date_format(self.metadata.start_time):
            needs_reload = True

        # Validate end_time format
        if not self.is_valid_date_format(self.metadata.end_time):
            needs_reload = True

        # Validate sampled_vol (not present in provided ExperimentMetadata, assumed to be air_volume)
        if not self.is_valid_sampled_vol(self.metadata.air_volume):
            #needs_reload = True
            self.metadata_air_volume = 1.0


        if needs_reload and not self.already_reloaded:
            self.already_reloaded = True  # Set flag to avoid reloading again
            self.load_metadata_from_raw_file(self.exp_name)

        #self.metadata.scan_start_timestamp = None
        #self.metadata.scan_end_timestamp = None


    def is_valid_date_format(self, date_str):
        try:
            datetime.strptime(date_str, "%Y-%m-%d %H:%M")
            return True
        except ValueError:
            return False

    def is_valid_sampled_vol(self, sampled_vol):
        if sampled_vol is None:
            return False
        try:
            sampled_vol_float = float(sampled_vol)
            return sampled_vol_float
        except (ValueError, TypeError):
            return False

    def load_metadata_from_raw_file(self, exp_name):
        # Implement your method to reload metadata from the raw file
        logging.warning("Loading metadata from raw file!")

        # Extract label from exp_name, assuming it's part of exp_name
        label = self.extract_label_from_exp_name(exp_name)
        if not label:
            logging.error(f"Unable to extract label from experiment name: {exp_name}")
            return None

        metadata = self._retrieve_metadata(label)
        self.metadata = metadata
        self.validate_and_correct_metadata()

        if metadata:
            self.metadata = metadata
            self.validate_and_correct_metadata()
            #self.metadata.scan_start_timestamp = None
            #self.metadata.scan_end_timestamp = None
            return self.metadata
        else:
            logging.error("Unable lo load metadata")
            return None

    def extract_label_from_exp_name(self, exp_name):
        # Implement your logic to extract label from exp_name
        return exp_name.split('_')[1]

    def _retrieve_metadata(self, label):
        station = stations_dict.get(label[0:3])
        if not station:
            logging.error(f"Station not found for label: {label}")
            return None

        try:
            date = datetime.strptime(label[3:], "%Y%m%d")
            directory_path = os.path.join(paths.external_data_path, 'sampler_raw_data', station['station_mapping'])
            date_str = date.strftime("%-d.%-m.%Y").strip()
        except ValueError:
            return None

        for root, dirs, files in os.walk(directory_path):
            for file_name in files:
                if file_name == "SUM.CSV":
                    sum_path = os.path.join(root, file_name)
                    with open(sum_path, "r") as file:
                        lines = file.readlines()
                        for line in lines[1:]:
                            fields = line.strip().split(";")
                            if len(fields) > 2 and fields[2].strip() == date_str.strip():
                                values = line.strip().split(";")
                                return self._create_experiment_metadata(values, label, "filter")

        logging.warning(f"No raw data found for label: {label}")
        return None

    def _create_experiment_metadata(self, values, label, experiment_type):
        start_datetime = datetime.strptime(values[2] + ' ' + values[3], "%d.%m.%Y %H:%M")
        end_datetime = datetime.strptime(values[4] + ' ' + values[5], "%d.%m.%Y %H:%M")
        metadata_dict = {
            'station': label[0:3],
            'experiment_type': experiment_type,
            'label': label,
            'sampler_id': f"{stations_dict[label[0:3]]['sampler_id']}",
            'sampler_status': values[1],
            'start_time': start_datetime.strftime("%Y-%m-%d %H:%M"),
            'end_time': end_datetime.strftime("%Y-%m-%d %H:%M"),
            'filter_position': int(values[7]),
            'air_volume': float(values[8]),
            'flow': float(values[9]),
            'temp': float(values[10]),
            'press': float(values[11]),
            'v_drop': 5e-05,
            'v_wash': 0.01,
            'dil_factor': 1.0,
            'filter_fraction': 1.0
        }
        return ExperimentMetadata(**metadata_dict)

    def import_metadata(self, import_path):
        # loads metadata from a file
        with open(import_path, "r") as import_file:
            metadata_dict = json.load(import_file)
            self.metadata = ExperimentMetadata(**metadata_dict)
            #self.metadata.scan_start_timestamp = None
            #self.metadata.scan_end_timestamp = None
        self.save_metadata_to_file()

    def export_metadata(self, export_format="json"):
        # exports metadata to a file in the specified format (JSON or YAML)
        #self.metadata.scan_start_timestamp = None
        #self.metadata.scan_end_timestamp = None
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
    str2date = lambda x: datetime.strptime(x, '%Y-%m-%d %H:%M:%S')
    data = np.genfromtxt(paths.raw_data_path / exp_name / 'sensors_data.csv',
                         delimiter=',',
                         dtype=None,
                         names=True,
                         converters={0: str2date})
    data = list(takewhile(lambda x: x['BT'] > -31, data))

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
    str2date = lambda x: datetime.strptime(x, '%Y-%m-%d %H:%M:%S')
    data = np.genfromtxt(paths.raw_data_path / exp_name / 'sensors_data.csv',
                         delimiter=',',
                         dtype=None,
                         names=True,
                         converters={0: str2date})
    data = list(takewhile(lambda x: x['BT'] > -31, data))
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


def calculate_freezing_temps(freezing_times, exp_name):
    str2date = lambda x: datetime.strptime(x, '%Y-%m-%d %H:%M:%S')
    data = np.genfromtxt(paths.raw_data_path / exp_name / 'sensors_data.csv',
                         delimiter=',',
                         dtype=None,
                         names=True,
                         converters={0: str2date})
    data = list(takewhile(lambda x: x['SP'] > -37, data))
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
