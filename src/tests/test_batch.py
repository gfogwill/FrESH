"""Batch analysis and the refreeze figure."""

import csv
import json
from datetime import datetime, timedelta

import cv2
import numpy as np
import pytest

from src import paths
from src.analysis import figures
from src.analysis.batch import (analyse_experiment, find_experiments,
                                write_combined, write_freezing_temps)

ROWS, COLS, R, PITCH, MARGIN = 2, 4, 10, 26, 20
N_FRAMES = 20
T_START, T_END = 0.0, -30.0


def plate_image(frozen, frame):
    h = MARGIN * 2 + PITCH * (ROWS - 1)
    w = MARGIN * 2 + PITCH * (COLS - 1)
    rng = np.random.default_rng(1000 + frame)
    img = np.clip(np.full((h, w), 40.0) + rng.normal(0, 2, (h, w)), 0, 255).astype(np.uint8)

    for k in range(ROWS * COLS):
        row, col = divmod(k, COLS)
        cv2.circle(img, (MARGIN + col * PITCH, MARGIN + row * PITCH), R,
                   190 if frozen[k] else 110, -1)

    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)


def well_positions():
    return np.array([[MARGIN + c * PITCH, MARGIN + r * PITCH, R]
                     for r in range(ROWS) for c in range(COLS)])


@pytest.fixture
def experiment(raw_data_dir):
    """A small plate where wells 0 and 1 freeze and the rest never do."""
    def build(name='202609180800_WBG20260918_c001', freeze_temps=None, cycle=1):
        freeze_temps = freeze_temps if freeze_temps is not None else \
            [-12.0, -18.0] + [None] * (ROWS * COLS - 2)

        folder = raw_data_dir / name
        (folder / 'pics').mkdir(parents=True)
        temps = np.linspace(T_START, T_END, N_FRAMES)
        rows = []

        for i, t in enumerate(temps):
            stamp = datetime(2026, 9, 18, 8, 0, 0) + timedelta(seconds=10 * i)
            frozen = [ft is not None and t <= ft for ft in freeze_temps]
            cv2.imwrite(str(folder / 'pics' / stamp.strftime('%Y%m%d%H%M%S.jpg')),
                        plate_image(frozen, i))
            rows.append(f"{stamp:%Y-%m-%d %H:%M:%S},{t:.2f},{t - 0.3:.2f},{t:.2f},{t:.2f}")

        (folder / 'sensors_data.csv').write_text(
            "datetime,SP,BT,RTD0,RTD1\n" + "\n".join(rows) + "\n")
        (folder / 'metadata.json').write_text(json.dumps({
            'label': 'WBG20260918', 'experiment_type': 'Water background',
            'station': 'WBG', 'cycle_number': cycle, 'series_id': '202609180800',
            'rotation': None, 'template_img': None, 'v_drop': 5e-05,
            'start_time': '2026-09-18 08:00', 'end_time': '2026-09-18 09:00'}))
        return name

    return build


# -- finding experiments ----------------------------------------------------

def test_experiments_are_found_by_pattern(experiment):
    experiment('202609180800_WBG20260918_c001', cycle=1)
    experiment('202609180800_WBG20260918_c002', cycle=2)
    experiment('202501010000_PAL20240619', cycle=None)

    assert find_experiments('202609180800_*') == ['202609180800_WBG20260918_c001',
                                                  '202609180800_WBG20260918_c002']
    assert find_experiments('nada*') == []


# -- the pipeline -----------------------------------------------------------

def test_only_the_wells_that_froze_get_a_temperature(experiment):
    """The point of the whole exercise: a background is mostly unfrozen."""
    name = experiment()

    result, _ = analyse_experiment(name, positions=well_positions(), min_step=5.0)

    assert result['frozen'] == 2
    assert result['unfrozen'] == ROWS * COLS - 2
    assert result['freezing_temps'][0] == pytest.approx(-12.0, abs=2.0)
    assert result['freezing_temps'][1] == pytest.approx(-18.0, abs=2.0)
    assert all(t is None for t in result['freezing_temps'][2:])


def test_without_a_threshold_every_well_is_declared_frozen(experiment):
    """Which is exactly the old behaviour, kept for the analysis window."""
    name = experiment()

    result, _ = analyse_experiment(name, positions=well_positions())

    assert result['frozen'] == ROWS * COLS


def test_a_window_rejects_freezing_that_is_too_warm(experiment):
    """t_start is the warm end: ignore anything that froze above it."""
    name = experiment()

    result, _ = analyse_experiment(name, positions=well_positions(),
                                   min_step=5.0, t_start=-15.0)

    assert result['freezing_temps'][0] is None      # froze at -12, too warm
    assert result['freezing_temps'][1] is not None  # froze at -18


def test_a_window_rejects_freezing_that_is_too_cold(experiment):
    """t_end is the cold end: ignore anything that froze below it."""
    name = experiment()

    result, _ = analyse_experiment(name, positions=well_positions(),
                                   min_step=5.0, t_end=-15.0)

    assert result['freezing_temps'][0] is not None  # froze at -12
    assert result['freezing_temps'][1] is None      # froze at -18, too cold


def test_auto_reads_the_threshold_off_the_data(experiment):
    name = experiment()

    result, _ = analyse_experiment(name, positions=well_positions(), min_step='auto')

    assert result['frozen'] == 2
    assert result['suggested_min_step'] > 0
    assert result['separation'] > 5


def test_the_cycle_number_comes_from_the_metadata(experiment):
    name = experiment(cycle=7)

    result, _ = analyse_experiment(name, positions=well_positions(), min_step=5.0)

    assert result['cycle'] == 7


def test_an_experiment_without_pictures_is_reported(raw_data_dir):
    (raw_data_dir / '202609180800_VACIO' / 'pics').mkdir(parents=True)
    (raw_data_dir / '202609180800_VACIO' / 'metadata.json').write_text(
        json.dumps({'label': 'VACIO', 'experiment_type': 'Filter'}))

    with pytest.raises(ValueError, match='no pictures'):
        analyse_experiment('202609180800_VACIO')


# -- the output files -------------------------------------------------------

def test_per_experiment_temperatures_are_written(raw_data_dir):
    path = write_freezing_temps('exp', [-12.0, None, -18.5])

    rows = list(csv.DictReader(open(path)))
    assert [r['freezing_temp'] for r in rows] == ['-12.000', '', '-18.500']
    assert [r['frozen'] for r in rows] == ['1', '0', '1']


def test_the_combined_table_has_one_row_per_well(raw_data_dir):
    results = [{'name': 'c1', 'cycle': 1, 'freezing_temps': [-12.0, None]},
               {'name': 'c2', 'cycle': 2, 'freezing_temps': [-13.0, -20.0]}]

    path = write_combined(results, paths.processed_data_path / 'combined.csv')

    rows = list(csv.DictReader(open(path)))
    assert len(rows) == 4
    assert rows[1] == {'experiment': 'c1', 'cycle': '1', 'well': '1',
                       'freezing_temp': '', 'frozen': '0'}


# -- the figure -------------------------------------------------------------

def test_the_table_is_read_back_by_cycle(raw_data_dir):
    results = [{'name': 'c1', 'cycle': 1, 'freezing_temps': [-12.0, None]},
               {'name': 'c2', 'cycle': 2, 'freezing_temps': [-13.0, -20.0]}]
    path = write_combined(results, paths.processed_data_path / 'combined.csv')

    by_cycle = figures.read_wells(path)

    assert by_cycle == {1: [-12.0, None], 2: [-13.0, -20.0]}


def test_unfrozen_wells_hold_the_frozen_fraction_down():
    grid = np.array([-10.0, -15.0, -25.0])

    ff = figures.frozen_fraction_curve([-12.0, -20.0, None, None], grid)

    assert list(ff) == [0.0, 0.25, 0.5]


def test_a_fully_frozen_plate_has_no_infinite_concentration():
    k = figures.cumulative_concentration(np.array([0.0, 0.5, 1.0]), 5e-05)

    assert np.isnan(k[0]) and np.isnan(k[2])
    assert np.isfinite(k[1])


def test_identical_cycles_show_no_drift():
    grid, curves = figures.build_curves(
        {1: [-12.0, -18.0, None], 2: [-12.0, -18.0, None]}, 5e-05)

    assert list(figures.drift(curves)) == pytest.approx([0.0, 0.0])
    assert np.allclose(figures.consecutive_differences(curves), 0.0)


def test_a_shifted_cycle_shows_up_as_drift():
    """The difference has to hold over a useful part of the range.

    The drift is a median across temperature, so one cycle freezing a single
    extra well at the very bottom deliberately does not move it.
    """
    grid, curves = figures.build_curves(
        {1: [-18.0, -19.0, None, None], 2: [-12.0, -13.0, -14.0, None]}, 5e-05)

    deltas = figures.drift(curves)

    assert deltas[0] < deltas[1], "the cycle that froze warmer must sit higher"


def test_one_extra_well_at_the_bottom_does_not_move_the_drift():
    grid, curves = figures.build_curves(
        {1: [-12.0, -18.0, None, None], 2: [-12.0, -18.0, -20.0, None]}, 5e-05)

    assert list(figures.drift(curves)) == pytest.approx([0.0, 0.0])


def test_a_table_where_nothing_froze_is_reported():
    with pytest.raises(ValueError, match='no well froze'):
        figures.build_curves({1: [None, None]}, 5e-05)


def test_the_figure_renders(tmp_path):
    grid, curves = figures.build_curves(
        {1: [-12.0, -18.0, None], 2: [-13.0, -19.0, None], 3: [-11.0, -17.0, None]}, 5e-05)

    fig = figures.plot(grid, curves, title='test')
    out = tmp_path / 'fig.png'
    fig.savefig(out)

    assert out.stat().st_size > 5000


def test_a_big_drift_is_not_cropped_out_of_the_panel():
    """The panel used to be fixed at +/-0.35, hiding any point beyond it."""
    grid, curves = figures.build_curves(
        {1: [-12.0] + [None] * 95, 2: [-12.0] * 96}, 5e-05)

    fig = figures.plot(grid, curves)
    low, high = fig.axes[1].get_ylim()
    deltas = figures.drift(curves)

    assert low <= np.nanmin(deltas) and np.nanmax(deltas) <= high
