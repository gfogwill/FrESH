import os

# The tests drive real Qt widgets, so run them without a display.
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PyQt6 import QtWidgets


@pytest.fixture(scope='session')
def qapp():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


@pytest.fixture
def raw_data_dir(tmp_path, monkeypatch):
    """Point the data paths at a temporary directory."""
    from src import paths

    for name in ('raw', 'interim', 'processed', 'external'):
        directory = tmp_path / name
        directory.mkdir()
        monkeypatch.setattr(paths, f'{name}_data_path', directory)

    return tmp_path / 'raw'
