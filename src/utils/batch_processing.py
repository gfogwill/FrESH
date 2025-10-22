import os
import sys
from src.experiment.experiment import FrESHExperiment
from src import paths

import csv
import logging
import json


def is_json_empty(filepath):
    try:
        if os.path.getsize(filepath) == 0:
            return True
        with open(filepath, 'r') as f:
            data = json.load(f)
            return data is None or data == {}
    except Exception:
        return True

def generate_metadata_from_alternate_sources(exp_path):
    # Placeholder - implement logic to create metadata.json from other sources
    print(f"Generating metadata.json for {exp_path} from alternate files...")
    pass

def batch_process(base_raw_path, station_code, status_log_file):
    status_dict = {}
    try:
        with open(status_log_file, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                status_dict[row['experiment']] = row
    except FileNotFoundError:
        pass

    with open(status_log_file, 'w', newline='') as f:
        fieldnames = ['experiment', 'status', 'error']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if f.tell() == 0:
            writer.writeheader()

        all_dirs = [d for d in os.listdir(base_raw_path) if os.path.isdir(os.path.join(base_raw_path, d))]
        experiments = [d for d in all_dirs if station_code.lower() in d.lower()]

        for exp in experiments:
            metadata_path = os.path.join(base_raw_path, exp, 'metadata.json')

            if is_json_empty(metadata_path):
                generate_metadata_from_alternate_sources(os.path.join(base_raw_path, exp))

            # Now safe to create FrESHExperiment instance
            try:
                experiment = FrESHExperiment(exp)
                experiment.run_analysis()
                print(f"Finished processing {exp}\n")
                writer.writerow({'experiment': exp, 'status': 'success', 'error': ''})
            except Exception as e:
                err_msg = str(e)
                print(f"Error processing {exp}: {err_msg}\n")
                writer.writerow({'experiment': exp, 'status': 'failure', 'error': err_msg})

            f.flush()


def clean_metadata_json(filepath):
    with open(filepath, 'r') as f:
        data = json.load(f)

    exp_desc = data.get('exp_description', '')
    if isinstance(exp_desc, str):
        data['exp_description'] = exp_desc.strip('"')

    with open(filepath, 'w') as f:
        json.dump(data, f, indent=4)


# Dentro de tu script principal, tras imports existentes:
from src.analysis.hub_batch import run_hub_for_experiment
from src import paths

def batch_process_new(base_raw_path, station_code, status_log_file):
    status_dict = {}
    try:
        with open(status_log_file, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                status_dict[row['experiment']] = row
    except FileNotFoundError:
        pass

    with open(status_log_file, 'w', newline='') as f:
        fieldnames = ['experiment', 'status', 'error']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if f.tell() == 0:
            writer.writeheader()

        all_dirs = [d for d in os.listdir(base_raw_path) if os.path.isdir(os.path.join(base_raw_path, d))]
        experiments = [d for d in all_dirs if station_code.lower() in d.lower()]

        for exp in experiments:
            exp_dir = os.path.join(base_raw_path, exp)
            metadata_path = os.path.join(exp_dir, 'metadata.json')

            if is_json_empty(metadata_path):
                generate_metadata_from_alternate_sources(exp_dir)

            try:
                # 1) Procesamiento FrESH
                experiment = FrESHExperiment(exp)
                experiment.run_analysis()

                # 2) HUB-backward y reporte
                res = run_hub_for_experiment(
                    exp_dir=exp_dir,
                    reports_dir=str(paths.reports_path),
                    nsubpop=2, disttype=1,
                    npoints=300, window_length=7, polyorder=2,
                    save_txt=True, save_pdf=True, plot_cumulative=True
                )
                print(f"Finished processing {exp} | HUB MSE={res['mse']:.4g} | Report: {res['out_base']}_report.pdf\n")
                writer.writerow({'experiment': exp, 'status': 'success', 'error': ''})
            except Exception as e:
                err_msg = str(e)
                print(f"Error processing {exp}: {err_msg}\n")
                writer.writerow({'experiment': exp, 'status': 'failure', 'error': err_msg})

            f.flush()


if __name__ == "__main__":
    # Adjust these paths and prefixes for your data layout and desired batch
    BASE_RAW_PATH = paths.raw_data_path
    # clean_metadata_json(BASE_RAW_PATH / '202404171336_KUO20240111' / 'metadata.json')

    STATUS_LOG_FILE = paths.reports_path / 'auto_processing_log.log'

    STATION_PREFIX = "KUO202406"  # Example selects all Kuopio 2024 experiments


    # Add project root to sys.path if necessary here for imports
    PROJECT_ROOT = paths.project_dir
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)

    batch_process_new(BASE_RAW_PATH, STATION_PREFIX, STATUS_LOG_FILE)
