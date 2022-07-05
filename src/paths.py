import os
import pathlib

# Get the project directory as the parent of this module locations
src_module_dir = pathlib.Path(os.path.dirname(os.path.abspath(__file__)))
project_dir = pathlib.Path(os.path.dirname(os.path.abspath(__file__))).parent

data_path = project_dir / 'data'
config_path = project_dir / 'config'

raw_data_path = data_path / 'raw'
interim_data_path = data_path / 'interim'
processed_data_path = data_path / 'processed'
external_data_path = data_path / 'external'

reports_path = project_dir / 'reports'
summary_path = reports_path / 'summary'
tables_path = reports_path / 'tables'
figures_path = reports_path / 'figures'

# model_path = project_dir / 'models'
# model_output_path = model_path / 'outputs'
# trained_model_path = model_path / 'trained'
