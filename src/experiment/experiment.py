import os
import json
import cv2

from datetime import datetime, timedelta
from itertools import takewhile

import numpy as np
import yaml
import csv
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
        self.bg_metadata = None
        self.is_analyzed = False
        self.background_corrected = False
        self.already_reloaded = False  # Flag to prevent infinite loop
        self.t = []
        self.spectra = None

        experiment_path = paths.raw_data_path / experiment_name
        processed_path = paths.processed_data_path / experiment_name

        # Create experiment directory if it doesn't exist
        if not os.path.exists(experiment_path):
            logging.info(f"Creating new experiment: {experiment_path}")
            os.mkdir(experiment_path)
            os.mkdir(experiment_path / 'pics')
        else:
            logging.info(f"Experiment found! Loading experiment: {experiment_path}")
            self.load_metadata()

            # Check if experiment has already been processed
            if os.path.exists(processed_path) and os.path.exists(processed_path / 'report.csv'):
                logging.info(f"Processed data found for experiment: {experiment_name}")
                self.is_analyzed = True

                # Try to load processed data
                try:
                    processed_data = self.get_processed_data()
                    # Extract freezing temperatures and other data if needed
                    if 'freezing_temp' in processed_data.dtype.names:
                        self.freezing_temps = processed_data['freezing_temp']
                    if 'ff' in processed_data.dtype.names:
                        self.ff = processed_data['ff']
                    logging.info(f"Successfully loaded processed data for {experiment_name}")
                except Exception as e:
                    logging.warning(f"Error loading processed data: {e}")
                    self.is_analyzed = False

        self.validate_and_correct_metadata()
        self.img_files = self.get_experiment_image_list()

        # Validate metadata completeness
        if self.metadata:
            self.validate_metadata_completeness()

    def validate_metadata_completeness(self):
        """Check if all required metadata fields are present and valid"""
        required_fields = ['label', 'start_time', 'end_time', 'experiment_type']

        if not self.metadata:
            logging.warning(f"No metadata found for experiment: {self.exp_name}")
            return False

        missing_fields = [field for field in required_fields
                          if not hasattr(self.metadata, field) or getattr(self.metadata, field) is None]

        if missing_fields:
            logging.warning(f"Missing required metadata fields: {', '.join(missing_fields)}")
            return False

        # Check numerical fields
        numerical_fields = ['air_volume', 'v_drop', 'v_wash', 'dil_factor', 'filter_fraction']
        for field in numerical_fields:
            if hasattr(self.metadata, field):
                value = getattr(self.metadata, field)
                if value is None or (isinstance(value, (int, float)) and value <= 0):
                    logging.warning(f"Invalid value for {field}: {value}")
                    return False

        return True

    def is_ready_for_analysis(self):
        """Check if the experiment has all required data for analysis"""
        if not self.metadata:
            return False, "Missing metadata"

        if not self.validate_metadata_completeness():
            return False, "Incomplete metadata"

        if not self.img_files or len(self.img_files) == 0:
            return False, "No images found"

        sensors_path = paths.raw_data_path / self.exp_name / 'sensors_data.csv'
        if not os.path.exists(sensors_path):
            return False, "Missing sensors data"

        return True, "Ready for analysis"

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

        img_file_list = self.get_experiment_image_list()
        self.grayscales_evolution = self.process_images(img_file_list)

        if existing_freezing_idxs is None:
            self.freezing_idxs = calculate_freezing_idxs(self.grayscales_evolution)

            self.del_indx = [i - 1 for i in self.metadata.del_index]
            self.freezing_idxs = np.delete(self.freezing_idxs, self.del_indx)

        else:
            self.freezing_idxs = existing_freezing_idxs


        freezing_times = calculate_freezing_times(img_file_list, self.freezing_idxs)

        self.freezing_temps = calculate_freezing_temps(freezing_times, self.exp_name)

        self.t, self.ff = process_sensors_data(self.exp_name, self.freezing_idxs, freezing_times)

        #background_experiment_save = self.metadata.background_exp

        # X is normalisation applied before bg correction, sampled volume correction is applied after

        self.calculate_normalisation_factor()

        X = self.metadata.normalisation_factor
        v_air = np.float64(self.metadata.air_volume)

        #print(f"normalization: {X}")

        # Concentration per sample
        self.conc_per_drop = - np.log(1 - np.array(self.ff)) * X # / v_drop is already calculated

        # Concentration per standar L of air
        self.conc_per_L = self.conc_per_drop / v_air
        # print('volume', v_air)

        self.spectra, self.background_corrected = spectra(self.freezing_temps, X, 1/v_air, 0.5, 1.96,
                                                          self.metadata.background_exp, 0)

        self.is_analyzed = True
        self.save_analysis_results()

    def save_analysis_results(self):
        """Save analysis results to processed and interim directories"""
        if not self.is_analyzed:
            logging.warning(f"Cannot save results for {self.exp_name} - experiment not analyzed yet")
            return False

        # Create directories if they don't exist
        interim_path = paths.interim_data_path / self.exp_name
        processed_path = paths.processed_data_path / self.exp_name
        interim_path.mkdir(parents=True, exist_ok=True)
        processed_path.mkdir(parents=True, exist_ok=True)

        # Save report.csv
        with open(processed_path / 'report.csv', 'w') as fo:
            fo.write(f'index,temp,ff,conc_per_L,conc_per_drop\n')
            for i in range(len(self.t)):
                fo.write(f'{i},{self.t[i]},{self.ff[i]},{self.conc_per_L[i]},{self.conc_per_drop[i]}\n')

        # Save spectra.csv
        with open(processed_path / 'spectra.csv', 'w') as fo:
            fo.write(f'temp,ff,ff_lower_conf_lvl,ff_upper_conf_lvl,k,k_lower_conf_lvl,')
            fo.write(f'k_upper_conf_lvl,K,K_lower_conf_lvl,K_upper_conf_lvl,{self.metadata.units}\n')

            for i in range(len(self.spectra)):
                fo.write(f'{self.spectra["temp"][i]},')
                fo.write(f'{self.spectra["ff"][i]},')
                fo.write(f'{self.spectra["ff_lower_conf_lvl"][i]},')
                fo.write(f'{self.spectra["ff_upper_conf_lvl"][i]},')
                fo.write(f'{self.spectra["k"][i]},')
                fo.write(f'{self.spectra["k_lower_conf_lvl"][i]},')
                fo.write(f'{self.spectra["k_upper_conf_lvl"][i]},')
                fo.write(f'{self.spectra["K"][i]},')
                fo.write(f'{self.spectra["K_lower_conf_lvl"][i]},')
                fo.write(f'{self.spectra["K_upper_conf_lvl"][i]}\n')

        # Save freezing_temps.csv
        with open(interim_path / 'freezing_temps.csv', 'w', newline='') as csv_file:
            csv_writer = csv.writer(csv_file)
            csv_writer.writerow(['Index', 'Temperature'])
            csv_writer.writerows(zip(*[iter(self.freezing_temps)] * 2))

        return True


    def calculate_normalisation_factor(self):
        v_drop = self.metadata.v_drop
        if self.metadata.experiment_type.lower()  in ['filter', 'filter Background']:
            nu = self.metadata.dil_factor
            v_wash = self.metadata.v_wash
            #v_air = self.metadata.air_volume # float(self.metadata.air_volume) # NOTE: after bg correction!
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
                filter_fraction = (0.5*d_punchout)**2 / (0.5*d_filter)**2
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

            img = auto_crop(img, self.metadata.template_img)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            res.append(circles.get_grayscales(gray, self.circles_positions))

        return np.array(res)

    def detect_circles(self):
        img = cv2.imread(str(self.img_files[0]))
        #print(self.metadata)

        if self.metadata.rotation is not None:
            img = cv2.rotate(img, self.metadata.rotation)

        if self.metadata.template_img is not None:
            # pass
            img = auto_crop(img, self.metadata.template_img)

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        self.circles_positions = circles.get_circles(gray, **self.metadata.hough_params, sort=True, plot=True)

    def get_img(self, frame_index, selected_droplet=None):

        if self.img_files is None or frame_index < 0 or frame_index >= len(self.img_files):
            return None

        img = cv2.imread(str(self.img_files[frame_index]))

        if self.metadata.rotation is not None:
            img = cv2.rotate(img, self.metadata.rotation)

        if self.metadata.template_img is not None:
            img = auto_crop(img, self.metadata.template_img)
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
            #print('\n Check metadata to be saved to a file', metadata_dict, '\n')
            json.dump(metadata_dict, metadata_file, indent=4)

    def load_metadata(self):
        metadata_path = os.path.join(paths.raw_data_path, self.exp_name, "metadata.json")
        #print(metadata_path)
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

    def validate_and_correct_metadata(self):
        # Fix station code if needed
        if self.metadata.station == "JFK" and hasattr(self.metadata, 'label') and self.metadata.label:
            station_code = self.metadata.label[0:3]
            if station_code in stations_dict:
                self.metadata.station = station_code

        # Set default values for numerical fields
        if self.metadata.dil_factor is None or (
                isinstance(self.metadata.dil_factor, int) and self.metadata.dil_factor == 1):
            self.metadata.dil_factor = 1.0

        if self.metadata.filter_fraction is None or (
                isinstance(self.metadata.filter_fraction, int) and self.metadata.filter_fraction == 1):
            self.metadata.filter_fraction = 1.0

        if self.metadata.v_wash is None:
            self.metadata.v_wash = 0.01

        # Try to load missing critical data from CSV
        if self.metadata.air_volume is None or self.metadata.start_time is None or self.metadata.end_time is None:
            self._load_metadata_from_csv()

        # Set defaults for remaining missing fields
        if self.metadata.air_volume is None:
            self.metadata.air_volume = 1.0

        if self.metadata.background_exp is None:
            self.metadata.background_exp = 'None'

        # Set default dates if still missing
        if self.metadata.start_time is None or not self.is_valid_date_format(self.metadata.start_time):
            if hasattr(self.metadata, 'label') and self.metadata.label and len(self.metadata.label) >= 11:
                try:
                    date_str = self.metadata.label[3:11]  # Extract YYYYMMDD
                    date_obj = datetime.strptime(date_str, "%Y%m%d")
                    self.metadata.start_time = date_obj.strftime("%Y-%m-%d") + " 08:00"
                    logging.warning(f"Using default start time from label: {self.metadata.start_time}")
                except ValueError:
                    logging.error(f"Cannot set default start date - invalid format in label: {self.metadata.label}")

        if self.metadata.end_time is None or not self.is_valid_date_format(self.metadata.end_time):
            if hasattr(self.metadata, 'label') and self.metadata.label and len(self.metadata.label) >= 11:
                try:
                    date_str = self.metadata.label[3:11]  # Extract YYYYMMDD
                    date_obj = datetime.strptime(date_str, "%Y%m%d") + timedelta(days=1)
                    self.metadata.end_time = date_obj.strftime("%Y-%m-%d") + " 08:00"
                    logging.warning(f"Using default end time from label: {self.metadata.end_time}")
                except ValueError:
                    logging.error(f"Cannot set default end date - invalid format in label: {self.metadata.label}")

        # Save the updated metadata
        self.save_metadata_to_file()

    def _load_metadata_from_csv(self):
        """Helper method to load metadata from CSV files"""
        if not hasattr(self.metadata, 'label') or not self.metadata.label:
            return

        station_code = self.metadata.label[0:3]
        date_str = self.metadata.label[3:]

        if station_code not in stations_dict:
            return

        station_mapping = stations_dict[station_code]['station_mapping']
        csv_path = os.path.join(paths.external_data_path, 'sampler_raw_data', station_mapping)

        if not os.path.exists(csv_path):
            logging.error(f"CSV path not found: {csv_path}")
            return

        try:
            date_obj = datetime.strptime(date_str, "%Y%m%d")
            formatted_date = date_obj.strftime("%d.%m.%y")

            csv_files = [f for f in os.listdir(csv_path) if f.endswith('.CSV')]

            for csv_file in csv_files:
                full_path = os.path.join(csv_path, csv_file)
                logging.info(f"Checking CSV file: {full_path}")

                with open(full_path, 'r') as f:
                    lines = f.readlines()

                    for line in lines[1:]:  # Skip header
                        if not line.strip():
                            continue

                        fields = line.strip().split(';')
                        if len(fields) < 9:
                            continue

                        # Check if date matches (accounting for different formats)
                        try:
                            csv_date_str = fields[2].strip()
                            csv_date = datetime.strptime(csv_date_str,
                                                         "%d.%m.%Y" if "." in csv_date_str else "%d.%m.%y")

                            if date_obj.day == csv_date.day and date_obj.month == csv_date.month:
                                logging.info(f"Found matching data for {date_str} in {csv_file}")

                                # Update metadata
                                date_format = "%d.%m.%Y" if "." in fields[2] else "%d.%m.%y"

                                if self.metadata.start_time is None:
                                    start_datetime = datetime.strptime(f"{fields[2]} {fields[3]}",
                                                                       f"{date_format} %H:%M")
                                    self.metadata.start_time = start_datetime.strftime("%Y-%m-%d %H:%M")

                                if self.metadata.end_time is None:
                                    end_datetime = datetime.strptime(f"{fields[4]} {fields[5]}", f"{date_format} %H:%M")
                                    self.metadata.end_time = end_datetime.strftime("%Y-%m-%d %H:%M")

                                if self.metadata.air_volume is None and len(fields) > 8:
                                    self.metadata.air_volume = float(fields[8].strip())

                                if self.metadata.flow is None and len(fields) > 9:
                                    self.metadata.flow = float(fields[9].strip())

                                if self.metadata.temp is None and len(fields) > 10:
                                    self.metadata.temp = float(fields[10].strip())

                                if self.metadata.press is None and len(fields) > 11:
                                    self.metadata.press = float(fields[11].strip())

                                if self.metadata.filter_position is None and len(fields) > 7:
                                    self.metadata.filter_position = int(fields[7].strip())

                                return  # Exit after finding matching data
                        except (ValueError, IndexError) as e:
                            logging.debug(f"Error parsing CSV line: {e}")
                            continue
        except Exception as e:
            logging.error(f"Error loading metadata from CSV: {e}")

    def is_valid_date_format(self, date_str):

        if date_str is None:
            return False
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
        logging.info(f"Loading metadata from raw file for {exp_name}")

        # Extract station code and date from experiment name
        parts = exp_name.split('_')
        if len(parts) < 2:
            logging.error(f"Invalid experiment name format: {exp_name}")
            return None

        label = parts[1]
        if len(label) < 11:  # Should be at least "UTO20240619"
            logging.error(f"Invalid label format: {label}")
            return None

        station_code = label[0:3]
        date_str = label[3:]

        # Get station mapping
        station = stations_dict.get(station_code)
        if not station or not station['station_mapping']:
            logging.error(f"Station mapping not found for {station_code}")
            return None

        # Find matching data in CSV
        try:
            date = datetime.strptime(date_str, "%Y%m%d")
            directory_path = os.path.join(paths.external_data_path, 'sampler_raw_data', station['station_mapping'])

            if not os.path.exists(directory_path):
                logging.error(f"Directory not found: {directory_path}")
                return None

            # Look for the most recent CSV file
            csv_files = [f for f in os.listdir(directory_path) if f.endswith('.CSV')]
            if not csv_files:
                logging.error(f"No CSV files found in {directory_path}")
                return None

            # Sort by modification time (newest first)
            csv_files.sort(key=lambda x: os.path.getmtime(os.path.join(directory_path, x)), reverse=True)

            # Format date for comparison with CSV
            formatted_date = date.strftime("%d.%m.%y")

            # Try each CSV file
            for csv_file in csv_files:
                file_path = os.path.join(directory_path, csv_file)
                with open(file_path, 'r') as file:
                    lines = file.readlines()

                    # Skip header
                    for line in lines[1:]:
                        fields = line.strip().split(';')
                        if len(fields) >= 6:  # Ensure we have enough fields
                            # Check if this line matches our date
                            if fields[2].strip() == formatted_date:
                                # Create metadata from this line
                                metadata = self._create_experiment_metadata(fields, label, "Filter")
                                self.metadata = metadata
                                self.save_metadata_to_file()
                                return metadata

            logging.warning(f"No matching data found for {label} in any CSV file")
            return None

        except Exception as e:
            logging.error(f"Error loading metadata from CSV: {str(e)}")
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


def read_sensors_data(file_path):
    # First, check the file structure
    with open(file_path, 'r') as f:
        header_line = f.readline().strip()
        first_data_line = f.readline().strip()

    # Handle missing column name for datetime
    if header_line.startswith(','):
        header_line = 'datetime' + header_line

    header = header_line.split(',')
    data_columns = first_data_line.split(',')

    # Convert string to datetime
    str2date = lambda x: datetime.strptime(x, '%Y-%m-%d %H:%M:%S')

    try:
        # Try to load with explicit names
        data = np.genfromtxt(file_path,
                             delimiter=',',
                             dtype=None,
                             names=header,
                             encoding=None,
                             skip_header=1,
                             converters={0: str2date})

        # Handle the case where only one row is returned
        if isinstance(data, np.void):
            data = np.array([data])

        return data
    except Exception as e:
        logging.warning(f"Error reading sensor data with standard approach: {e}")

        # Fallback to explicit column names
        column_names = ['datetime', 'SP', 'BT', 'T1', 'RTD0']

        try:
            data = np.genfromtxt(file_path,
                                 delimiter=',',
                                 dtype=None,
                                 names=column_names,
                                 encoding=None,
                                 skip_header=1,
                                 converters={0: str2date})

            # Handle the case where only one row is returned
            if isinstance(data, np.void):
                data = np.array([data])

            return data
        except Exception as e:
            logging.error(f"Failed to read sensors data with fallback approach: {e}")
            # Return minimal valid data structure
            dtype = [('datetime', 'O'), ('SP', '<f8'), ('BT', '<f8'), ('T1', '<f8'), ('RTD0', '<f8')]
            return np.array([(datetime.now(), 0.0, 0.0, 0.0, 0.0)], dtype=dtype)


def process_sensors_data(exp_name, freezing_idxs, freezing_times):
    file_path = paths.raw_data_path / exp_name / 'sensors_data.csv'
    data = read_sensors_data(file_path)

    # Filter data
    data = list(takewhile(lambda x: x['BT'] > -45, data))

    t = []
    ff = []

    for line in data:
        t.append(line['T1'])
        ff.append((freezing_times <= line['datetime']).sum() / len(freezing_idxs))

    return t, ff


def calculate_frame_temperatures(img_files, exp_name):
    times = [datetime.strptime(img.stem, "%Y%m%d%H%M%S") for img in img_files]
    file_path = paths.raw_data_path / exp_name / 'sensors_data.csv'

    data = read_sensors_data(file_path)
    data = list(takewhile(lambda x: x['BT'] > -45, data))

    t = []
    for time in times:
        matching_data = next((line['T1'] for line in data if line['datetime'] == time), None)
        if matching_data is None:
            nearest = min(data, key=lambda line: abs(line['datetime'] - time))
            t.append(nearest['T1'])
        else:
            t.append(matching_data)

    return t


def calculate_freezing_temps(freezing_times, exp_name):
    file_path = paths.raw_data_path / exp_name / 'sensors_data.csv'
    data = read_sensors_data(file_path)

    # Filter data
    data = list(takewhile(lambda x: x['SP'] > -45, data))

    t = []
    for index, time in enumerate(freezing_times):
        matching_data = next((line['T1'] for line in data if line['datetime'] == time), None)
        if matching_data is None:
            nearest_data = min(data, key=lambda line: abs(line['datetime'] - time))
            t.extend([index, nearest_data['T1']])
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
