import logging

from PyQt6 import QtWidgets, uic, QtGui
from PyQt6.QtWidgets import QComboBox, QLineEdit, QTextEdit
import pyqtgraph as pg

import cv2

from src import paths
from src.experiment.experiment import FrESHExperiment, calculate_frame_temperatures
from src.gui.experiment_gui import convert_cv_qt

import os
import pathlib
import numpy as np
import json
from datetime import datetime

rotation_dict = {'-': None,
                 '90 CCW': cv2.ROTATE_90_COUNTERCLOCKWISE,
                 '90 CW': cv2.ROTATE_90_CLOCKWISE,
                 '180': cv2.ROTATE_180}


def copy_to_clipboard_linux(text):
    command = 'echo -n "' + text + '" | xclip -selection clipboard'
    os.system(command)


# --- metadata <-> widget conversion ----------------------------------------
#
# Every value used to be pushed into a widget with str(), so a field that was
# never filled in showed the literal text "None" -- and reading it back tried to
# parse "None" as a date, which is why an experiment without a start and end
# time could not be saved without typing something dummy first. None now means
# an empty field, in both directions.

#: Experiment types that can be picked as a background for another experiment.
#: Matched case-insensitively; the set used to contain "Field backgrouund", so
#: field backgrounds never appeared in the dropdown at all.
BACKGROUND_TYPES = {'water background', 'filter background',
                    'punched filter background', 'field background'}

#: Metadata fields holding a timestamp.
TIME_FIELDS = ('start_time', 'end_time')

#: Accepted spellings when reading a timestamp back out of a widget.
TIME_FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d",
                "%d.%m.%Y %H:%M", "%d.%m.%Y")

#: How a timestamp is stored in metadata.json.
TIME_FORMAT = "%Y-%m-%d %H:%M"

#: Fields that must come back as numbers rather than as strings.
FLOAT_FIELDS = ('air_volume', 'temp', 'press', 'flow', 'v_drop', 'v_wash',
                'dil_factor', 'filter_fraction', 'normalisation_factor',
                'filter_diameter', 'puncher_diameter', 'latitude', 'longitude')
INT_FIELDS = ('filter_position',)

#: Text that means "no value". Older metadata.json files have the string
#: "None" stored where a real null belongs.
EMPTY_TEXTS = ('', 'none', 'null', 'nan')


def widget_text(value):
    """Render a metadata value for a widget. None shows as an empty field."""
    if value is None:
        return ''
    if isinstance(value, datetime):
        return value.strftime(TIME_FORMAT)
    return str(value)


def parse_field(attribute_name, text):
    """Turn what is in a widget back into a metadata value.

    An empty field is None, not the string "None"; timestamps come back
    normalised to TIME_FORMAT and numbers come back as numbers. Anything that
    cannot be parsed is reported and stored as None rather than raising, so one
    bad field cannot stop the whole form from being saved.
    """
    text = (text or '').strip()

    if text.lower() in EMPTY_TEXTS:
        return None

    if attribute_name in TIME_FIELDS:
        for fmt in TIME_FORMATS:
            try:
                return datetime.strptime(text, fmt).strftime(TIME_FORMAT)
            except ValueError:
                continue
        logging.warning(f"{attribute_name}: {text!r} is not a date "
                        f"(expected e.g. 2024-06-19 08:00); left empty")
        return None

    if attribute_name in FLOAT_FIELDS:
        try:
            return float(text)
        except ValueError:
            logging.warning(f"{attribute_name}: {text!r} is not a number; left empty")
            return None

    if attribute_name in INT_FIELDS:
        try:
            return int(float(text))
        except ValueError:
            logging.warning(f"{attribute_name}: {text!r} is not a whole number; left empty")
            return None

    return text


class ExperimentAnalysisUi(QtWidgets.QMainWindow):
    def __init__(self, *args, **kwargs):
        super(ExperimentAnalysisUi, self).__init__(*args, **kwargs)

        self.metadata_modified = False  # Flag to track if metadata has been modified

        self.experiment = None

        self.selected_droplet = None
        self.grayscales_evolution = None
        self.del_indx = []
        self.t = []
        self.ff = []
        self.frame_t = []

        self.bg_t = []
        self.bg_ff = []

        self.template_img = None

        uic.loadUi(paths.src_module_dir / 'gui' / 'analysis.ui', self)

        self.experiment_list_view = self.findChild(QtWidgets.QListView, 'experimentListView')
        self.model = QtGui.QStandardItemModel(self.experiment_list_view)
        self.experiment_list_view.setModel(self.model)

        self.filter_line_edit = self.findChild(QtWidgets.QLineEdit, 'filter_line_edit')
        self.filter_line_edit.textChanged.connect(self.filter_exp_names)

        self.button_load_experiment = self.findChild(QtWidgets.QPushButton, 'loadExperimentButton')
        self.button_load_experiment.clicked.connect(self.load_experiment)

        # List of attribute names
        attribute_names = [
            "station", "label", "sampler_id",
            "sampler_status", "filter_position", "air_volume", "start_time", "end_time", "v_drop"
        ]

        # Generate lines for finding child widgets
        for attribute_name in attribute_names:
            setattr(self, f"{attribute_name}_text_edit", self.findChild(QtWidgets.QLineEdit, f'{attribute_name}_text_edit'))

        self.type_combobox = self.findChild(QtWidgets.QComboBox, 'comboBox_type')
        self.exp_description_line_edit = self.findChild(QtWidgets.QTextEdit, "exp_description_text_edit")

        # ToDo: put in another place the code
        self.button_run_analysis = self.findChild(QtWidgets.QPushButton, 'runButton')
        self.button_run_analysis.clicked.connect(self.run_analysis)

        # self.button_detect = self.findChild(QtWidgets.QPushButton, "pushButton_Detect")
        # self.button_detect.clicked.connect(self.detect_circles)

        # self.button_detect = self.findChild(QtWidgets.QPushButton, "pushButton_Lock")
        # self.button_detect.clicked.connect(self.lock_circles)

        self.button_save = self.findChild(QtWidgets.QPushButton, 'saveButton')
        self.button_save.clicked.connect(self.save)
        
        self.box_selected_droplet = self.findChild(QtWidgets.QComboBox, 'droplet_combo_box')
        self.box_selected_droplet.activated.connect(self.droplet_combobox_activated)
        
        self.box_change_temp = self.findChild(QtWidgets.QComboBox, 'temp_combo_box')
        self.box_change_temp.activated.connect(self.temp_combobox_activated)
        
        self.button_change_indx = self.findChild(QtWidgets.QPushButton, 'change_button')
        self.button_change_indx.clicked.connect(self.change_freezing_indx) # self.analyze_exsisting_freezing_idx
        #self.button_change_indx.clicked.connect(self.analyze_exsisting_freezing_idx)
        
        # Add page for punched filter metadata 
        self.stackedWidget = self.findChild(QtWidgets.QStackedWidget, "stackedWidget")  
        
        self.filter_page = self.findChild(QtWidgets.QWidget, "filter_page")
        self.punched_page = self.findChild(QtWidgets.QWidget, "punched_filter_page")
        self.water_background_page = self.findChild(QtWidgets.QWidget, "water_background_page")
        self.filter_background_page = self.findChild(QtWidgets.QWidget, "filter_background_page")
        
        self.page_mapping = {
            "Water background": self.stackedWidget.indexOf(self.water_background_page),
            "Filter": self.stackedWidget.indexOf(self.filter_page),
            "Filter background": self.stackedWidget.indexOf(self.filter_background_page),
            "Punched filter": self.stackedWidget.indexOf(self.punched_page),
            "Punched filter background": self.stackedWidget.indexOf(self.punched_filter_background_page)
        }
        
        self.type_combobox.currentTextChanged.connect(self.switch_exp_type)
        # connect all the text edits together 
        self.shared_exp_description = QtGui.QTextDocument()
        self.findChild(QtWidgets.QTextEdit, "exp_description_text_edit_wb").setDocument(self.shared_exp_description)
        self.findChild(QtWidgets.QTextEdit, "exp_description_text_edit").setDocument(self.shared_exp_description)
        self.findChild(QtWidgets.QTextEdit,
        		"exp_description_text_edit_filterbg").setDocument(self.shared_exp_description)
        self.findChild(QtWidgets.QTextEdit, "exp_description_text_edit_punch").setDocument(self.shared_exp_description)
        self.findChild(QtWidgets.QTextEdit,
        		"exp_description_text_edit_punch_bg").setDocument(self.shared_exp_description)

        self.button_scan_start = self.findChild(QtWidgets.QPushButton, 'set_scan_start_button')
        self.button_scan_start.clicked.connect(self.update_scan_start)

        self.button_scan_end = self.findChild(QtWidgets.QPushButton, 'set_scan_end_button')
        self.button_scan_end.clicked.connect(self.update_scan_end)

        self.image_frame = self.findChild(QtWidgets.QLabel, 'img_label')
        self.image_frame.setScaledContents(True)

        self.templates_combobox = self.findChild(QtWidgets.QComboBox, 'comboBox_templates')
        self.populate_combobox_templates()
        self.templates_combobox.currentTextChanged.connect(self.update_template_img)

        self.label_temp = self.findChild(QtWidgets.QLabel, 'temp_label')

        self.rotation_combobox = self.findChild(QtWidgets.QComboBox, 'comboBox_rotation')
        self.rotation_combobox.currentTextChanged.connect(self.update_rotation)

        self.horizontalSlider_13.valueChanged['int'].connect(lambda value: self.update_hough_dict_param("min_distance", value))
        self.horizontalSlider_14.valueChanged['int'].connect(lambda value: self.update_hough_dict_param("param1", value))
        self.horizontalSlider_15.valueChanged['int'].connect(lambda value: self.update_hough_dict_param("param2", value))
        self.horizontalSlider_16.valueChanged['int'].connect(lambda value: self.update_hough_dict_param("min_radius", value))
        self.horizontalSlider_17.valueChanged['int'].connect(lambda value: self.update_hough_dict_param("max_radius", value))

        self.framesSlider.valueChanged['int'].connect(self.update_img)
        
        self.common_attributes = {
            "label": self.label_text_edit, 
            "experiment_type": self.type_combobox, 
            "start_time": self.start_time_text_edit, 
            "end_time": self.end_time_text_edit, 
            "station": self.station_text_edit,
            "air_volume": self.air_volume_text_edit,
            "temp": self.temp_text_edit, 
            "press": self.press_text_edit, 
            "exp_description": self.exp_description_text_edit,
            "template_img": self.templates_combobox,
            "v_drop": self.v_drop_text_edit, 
            "normalisation_factor": self.normalisation_factor_text_edit,
            "units" : self.units_text_edit
            }

        self.filter_attributes = {
            
            "sampler_id": self.sampler_id_text_edit,
            "sampler_status": self.sampler_status_text_edit,
            "filter_position": self.filter_position_text_edit,
            "flow": self.flow_text_edit,
            "filter_fraction": self.filter_fraction_text_edit,
            "v_wash": self.wash_vol_text_edit,
            "dil_factor": self.dil_factor_text_edit,
            "background_exp": self.background_combobox,
            }
            
        self.punched_filter_attributes = {
           "filter_diameter": self.filter_diameter_text_edit_punch,
           "puncher_diameter": self.puncher_diameter_text_edit,
           "filter_type": self.filter_type_text_edit_punch,
           "latitude": self.latitude_text_edit_punch,
           "longitude": self.longitude_text_edit_punch,
           "background_exp_punch": self.background_combobox_punch,
           }
           
        self.background_combobox.currentTextChanged.connect(self.get_background)

        self.attribute_to_widget_mapping = {**self.common_attributes, **self.filter_attributes,
        					**self.punched_filter_attributes}

        self._connect_metadata_widgets()

        self.FFwidget.setLabel('left', 'Frozen Fraction', color='red', size=30)

        self.image_frame.mousePressEvent = self.mouse_clicked

        self.populate_experiment_list()


    def load_metadata_from_gui(self):
        # metadata = ExperimentMetadata()  # Assuming ExperimentMetadata is a class to hold metadata

        # Load metadata from text edits
        for attribute_name, widget in self.attribute_to_widget_mapping.items():
            if widget is None:
                continue

            if isinstance(widget, QComboBox):
                value = widget.currentText()
            elif isinstance(widget, (QLineEdit, QTextEdit)):
                value = widget.toPlainText() if isinstance(widget, QTextEdit) else widget.text()
            else:
                continue

            setattr(self.experiment.metadata, attribute_name,
                    parse_field(attribute_name, value))

        return self.experiment.metadata

    def update_metadata_description(self):
        self.update_metadata('exp_description', self.exp_description_line_edit.toPlainText())

    def update_scan_start(self):
        frame = self.framesSlider.value()

        self.experiment.metadata.scan_start_timestamp = str(self.experiment.img_files[frame].stem)
        self.experiment.save_metadata_to_file()
        self.load_experiment()

    def update_scan_end(self):
        frame = self.framesSlider.value()

        self.experiment.metadata.scan_end_timestamp = str(self.experiment.img_files[frame].stem)
        self.experiment.save_metadata_to_file()
        self.load_experiment()

    def load_metadata_into_gui(self, metadata):
        """Show the metadata in the form.

        Signals are blocked while filling in: the widgets are being set from
        the metadata, not edited by anybody, so this must not mark the
        experiment as modified. The edit signals are connected once, in
        _connect_metadata_widgets, rather than every time an experiment is
        loaded -- doing it here stacked one more connection per load, so after
        opening five experiments every keystroke fired five updates.
        """
        for attribute_name, widget in self.attribute_to_widget_mapping.items():
            if widget is None:
                continue

            value = widget_text(getattr(metadata, attribute_name, None))

            blocked = widget.blockSignals(True)
            try:
                if isinstance(widget, QComboBox):
                    index = widget.findText(value)
                    if index < 0 and value:
                        widget.addItem(value)
                        index = widget.findText(value)
                    widget.setCurrentIndex(index)
                else:
                    widget.setText(value)
            finally:
                widget.blockSignals(blocked)

    def _connect_metadata_widgets(self):
        """Wire every metadata widget to update_metadata, exactly once."""
        for attribute_name, widget in self.attribute_to_widget_mapping.items():
            if widget is None:
                continue

            if isinstance(widget, QComboBox):
                signal = widget.currentTextChanged
            elif isinstance(widget, QTextEdit):
                signal = widget.textChanged
            else:
                signal = widget.textChanged

            if isinstance(widget, QTextEdit):
                # QTextEdit.textChanged carries no text.
                signal.connect(lambda name=attribute_name, w=widget:
                               self.update_metadata(name, w.toPlainText()))
            else:
                signal.connect(lambda text, name=attribute_name:
                               self.update_metadata(name, text))

    def update_metadata(self, attribute_name, new_value):
        """Store one edited field, converted to its proper type."""
        if self.experiment is None or self.experiment.metadata is None:
            return  # nothing loaded yet

        metadata = self.experiment.metadata
        if not hasattr(metadata, attribute_name):
            return

        setattr(metadata, attribute_name, parse_field(attribute_name, new_value))
        self.show_metadata_alert()

    def populate_combobox_templates(self):
        png_files = [file for file in os.listdir(paths.etc_path) if file.endswith(".png") or file.endswith(".jpg")]
        self.templates_combobox.addItems(png_files)
        self.template_img = self.templates_combobox.currentText()

    def update_template_img(self):
        template_img = self.templates_combobox.currentText()

        self.experiment.metadata.template_img = template_img
        self.show_metadata_alert()

        template_image = cv2.imread(str(paths.etc_path / template_img))

        self.image_frame.setFixedWidth(template_image.shape[1])
        self.image_frame.setFixedHeight(template_image.shape[0])

        self.update_img()

    def update_rotation(self):
        rotation = self.rotation_combobox.currentText()

        self.experiment.metadata.rotation = rotation_dict[rotation]
        self.show_metadata_alert()
        self.update_img()

    def run_analysis(self):
        self.experiment.run_analysis()

        frame = self.framesSlider.value()
        self.normalisation_factor_text_edit.setText(f'{float(self.experiment.metadata.normalisation_factor)}')

        if self.experiment.is_analyzed:
            self.update_ff_plot()

    def populate_experiment_list(self):
        # Clear the model
        self.model.clear()

        # Load and display exp_names
        listdir = os.listdir(paths.raw_data_path)
        listdir.sort(reverse=True)

        for exp_name in listdir:
            item = QtGui.QStandardItem(exp_name)
            item.setEditable(False)
            self.model.appendRow(item)

    def update_hough_dict_param(self, param_name, new_value):
        self.experiment.metadata.hough_params[param_name] = new_value
        self.experiment.detect_circles()
        self.show_metadata_alert()

    def mouse_clicked(self, evt):
        x = evt.pos().x()
        y = evt.pos().y()

        frame = self.framesSlider.value()

        if hasattr(self.experiment, "circles_positions"):
            self.selected_droplet = np.argmin(np.linalg.norm(self.experiment.circles_positions[:, :2] - np.array([x, y]), axis=1))
            print(f'clicked plot X: {x}, Y: {y}, circle: {self.selected_droplet}')

            self.FFwidget_grayscale.clear()
            self.FFwidget_grayscale.plot(self.frame_t, self.experiment.grayscales_evolution[:, self.selected_droplet])

        self.FFwidget_grayscale.plot([self.frame_t[frame], self.frame_t[frame]], self.FFwidget_grayscale.getAxis('left').range)
        self.update_img()

    def filter_exp_names(self):
        # Get the filter text
        filter_texts = [filter_text.strip().upper() for filter_text in self.filter_line_edit.text().split('&')]
        # Clear the model
        self.model.clear()

        # Load and display filtered exp_names
        listdir = os.listdir(paths.raw_data_path)
        listdir.sort(reverse=True)

        for exp_name in listdir:
            if all(filter_text in exp_name.upper() for filter_text in filter_texts):
                item = QtGui.QStandardItem(exp_name)
                item.setEditable(False)
                self.model.appendRow(item)

    def change_freezing_indx(self):
        # find the index of the temperature at hand
    	if self.selected_droplet is not None:
            target_temp = float(self.box_change_temp.currentText())
            index = self.frame_t.index(target_temp)
            self.experiment.freezing_idxs[self.selected_droplet] = index
            self.experiment.run_analysis(self.experiment.freezing_idxs)
            self.update_img()

        #else:
        #    print('No selected droplet found')

    def analyze_exsisting_freezing_idx(self):
        # read temperatures form file and loop through them and use change_freezing_indx
        correct_file = os.path.join(paths.etc_path / 'ODEN_200108bg.csv')
        data = np.genfromtxt(correct_file, delimiter=',',skip_header=1)
        print(data)
        for i in range(len(data[:,0])):
            selected_droplet = int(data[:,0][i])
            target_temp = np.float64(data[:,1][i])
            index = self.frame_t.index(target_temp)
            self.experiment.freezing_idxs[selected_droplet] = index
        self.experiment.run_analysis(self.experiment.freezing_idxs)
        self.update_img()

    def droplet_combobox_activated(self):
        self.selected_droplet= int(self.box_selected_droplet.currentText())
        self.update_img()

    def temp_combobox_activated(self):
        # for now, it seems this is not required :)
        pass

    def switch_exp_type(self):
        """Switch the stacked widget page based on the combo box text."""
        text = self.type_combobox.currentText()

        if text in self.page_mapping:
            self.stackedWidget.setCurrentIndex(self.page_mapping[text])
            self.stackedWidget.update()  # Ensure UI refresh
        else:
            print("Page not found in mapping!")

    def filter_background_folders(self):
        """Processed experiments that can be used as a background.

        The parameter used to be called ``folder_list`` with no ``self``, so the
        instance was being passed in as it and then thrown away on the first
        line -- it only worked because nothing read the argument.
        """
        filtered_folders = []

        for folder in os.listdir(paths.processed_data_path):
            metadata_path = paths.raw_data_path / folder / "metadata.json"

            if not metadata_path.exists():
                continue

            try:
                with open(metadata_path, "r", encoding="utf-8") as file:
                    data = json.load(file)
            except (OSError, json.JSONDecodeError) as e:
                logging.warning(f"Could not read the metadata of {folder}: {e}")
                continue

            if str(data.get("experiment_type", '')).strip().lower() in BACKGROUND_TYPES:
                filtered_folders.append(folder)

        return sorted(filtered_folders)

    def get_background(self):
        if self.experiment is not None:
            background = self.background_combobox.currentText()
            if self.experiment.is_analyzed:
                if background is not None and background != 'None' and background != '':
                    try:
                        path = os.path.join(paths.processed_data_path, background, 'report.csv')
                        background_data = np.genfromtxt(path, delimiter=',', names=True)
                        self.bg_t, self.bg_ff = background_data['temp'], background_data['ff']
                    except:
                        print('Background experiment could not be loaded')
                else:
                    #print('\n No background \n')
                    self.bg_t, self.bg_ff = [], []
                self.update_ff_plot()

    def update_ff_plot(self, frame=0):
        frame = self.framesSlider.value()
        self.FFwidget.clear()
        self.FFwidget.plot(self.bg_t, self.bg_ff, pen=pg.mkPen(color='b'))
        self.FFwidget.plot(self.experiment.t, self.experiment.ff, pen=pg.mkPen(color='r'))
        self.FFwidget.plot([self.frame_t[frame], self.frame_t[frame]], self.FFwidget.getAxis('left').range)


    def save(self):
        i = pathlib.Path(paths.interim_data_path / self.exp_name)
        i.mkdir(parents=True, exist_ok=True)

        self.experiment.metadata = self.load_metadata_from_gui()
        # for now, don't save the scan time edits to avoid errors in loading back the metadata
        #self.experiment.metadata.scan_start_timestamp = None
        #self.experiment.metadata.scan_end_timestamp = None

        self.experiment.save_metadata_to_file()

        # Save metadata to a file
        if self.metadata_modified:
            self.metadata_modified = False
            self.hide_metadata_alert()

        # Save analysis results if analyzed
        if self.experiment.is_analyzed:
            self.experiment.save_analysis_results()

    def show_metadata_alert(self):
        # Show an alert to inform the user that metadata has been modified
        if self.exp_name is None:
            return
        self.metadata_modified = True
        self.setWindowTitle(self.exp_name + "*")

    def hide_metadata_alert(self):
        # Hide the metadata modification alert
        self.metadata_modified = False
        self.setWindowTitle(self.exp_name)

    def update_img(self):
        frame = self.framesSlider.value()

        self.frameNumber.setText('Image: ' + str(self.experiment.img_files[frame].stem))
        self.label_temp.setText('Temperature: ' + str(self.frame_t[frame]))
        self.box_change_temp.setCurrentText(str(self.frame_t[frame]))
        

        img = self.experiment.get_img(frame, self.selected_droplet)
        #img = cv2.resize(img, (img.shape[1] * 2, img.shape[0] * 2), interpolation=cv2.INTER_CUBIC)

        qt_img = convert_cv_qt(img)
        self.image_frame.setPixmap(qt_img)

        if self.experiment.is_analyzed:
            self.update_ff_plot()

        if hasattr(self.experiment, "circles_positions") and self.selected_droplet is not None:
            self.FFwidget_grayscale.clear()
            self.FFwidget_grayscale.plot(self.frame_t, self.experiment.grayscales_evolution[:, self.selected_droplet])
            self.FFwidget_grayscale.plot([self.frame_t[frame], self.frame_t[frame]],
                                     self.FFwidget_grayscale.getAxis('left').range)

    def load_experiment(self):
        self.selected_droplet = None
        self.exp_name = self.experiment_list_view.currentIndex().data()

        copy_to_clipboard_linux(self.exp_name)

        self.setWindowTitle(self.exp_name)
        
        bg_exps = self.filter_background_folders()
        self.background_combobox.clear()
        self.background_combobox.addItem('None')
        self.background_combobox.addItems(bg_exps)
        self.background_combobox_punch.clear()
        self.background_combobox_punch.addItem('None')
        self.background_combobox_punch.addItems(bg_exps)
        
        print('\n loading experiment', self.exp_name, '\n')
        
        self.experiment = FrESHExperiment(self.exp_name)
        
        self.framesSlider.setValue(0)
        self.framesSlider.setMaximum(self.experiment.img_files.__len__() - 1)
        self.frame_t = calculate_frame_temperatures(self.experiment.img_files, self.exp_name)

        self.load_metadata_into_gui(self.experiment.metadata)
        
        self.experiment.detect_circles()

        img = self.experiment.get_img(0)
        #img = cv2.resize(img, (img.shape[1] * 2, img.shape[0] * 2), interpolation=cv2.INTER_CUBIC)

        qt_img = convert_cv_qt(img)
        self.image_frame.setPixmap(qt_img)

        self.run_analysis()
        self.update_img()
        self.hide_metadata_alert()

        if not self.experiment.is_analyzed:
            self.experiment.run_analysis()
            self.normalisation_factor_text_edit.setText(f'{float(self.experiment.metadata.normalisation_factor)}')

            if self.experiment.is_analyzed:
                self.box_selected_droplet.setCurrentIndex(-1)
                self.box_change_temp.addItems([str(i) for i in self.frame_t])
                self.get_background()
                #self.update_ff_plot()



