#!/usr/bin/env python3
"""Analyse a set of experiments in one go.

    python -m src.analysis.batch '202609181200_WBG*'
    python -m src.analysis.batch '*WBG*' --t-start -5 --t-end -30

For every matching folder under ``data/raw`` this detects the wells, follows
each well through the pictures, and works out the temperature at which it
froze. It writes, per experiment, ``data/interim/<name>/freezing_temps.csv``,
and for the whole set one tidy table -- one row per well per experiment --
that :mod:`src.analysis.figures` turns into the refreeze plot.

The wells are detected **once**, on the first experiment, and those positions
are reused for the rest. Detecting them per experiment lets the count come out
at 95 or 97, and since the wells are ordered by cutting the list into rows of
12, one missing circle shifts every well after it: well 40 of one cycle would
not be well 40 of the next.
"""

import argparse
import csv
import fnmatch
import logging
import sys

import numpy as np

from src import paths
from src.analysis import circles
from src.analysis.circles import auto_crop
from src.analysis.detection import (detect_freezing_frames, suggest_min_step,
                                    summarise)
from src.experiment.experiment import FrESHExperiment, calculate_frame_temperatures

import cv2

#: Wells on a plate, and how many per row. Used to warn when detection
#: disagrees with the plate.
WELLS_PER_PLATE = 96
WELLS_PER_ROW = 12

COMBINED_COLUMNS = ('experiment', 'cycle', 'well', 'freezing_temp', 'frozen')


def find_experiments(pattern):
    """Experiment folders under data/raw matching a shell-style pattern."""
    if not paths.raw_data_path.is_dir():
        return []

    names = [p.name for p in paths.raw_data_path.iterdir()
             if p.is_dir() and fnmatch.fnmatch(p.name, pattern)]
    return sorted(names)


def detect_wells(experiment):
    """Well positions from an experiment's first picture."""
    if not experiment.img_files:
        raise ValueError(f"{experiment.exp_name} has no pictures")

    image = cv2.imread(str(experiment.img_files[0]))
    if image is None:
        raise ValueError(f"could not read {experiment.img_files[0]}")

    if experiment.metadata.rotation is not None:
        image = cv2.rotate(image, experiment.metadata.rotation)
    if experiment.metadata.template_img is not None:
        image = auto_crop(image, experiment.metadata.template_img)

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    positions = circles.get_circles(gray, **experiment.metadata.hough_params,
                                    sort=True, plot=False)

    if len(positions) != WELLS_PER_PLATE:
        logging.warning(
            f"{len(positions)} wells detected on {experiment.exp_name}, expected "
            f"{WELLS_PER_PLATE}. The ordering cuts the list into rows of "
            f"{WELLS_PER_ROW}, so a wrong count shifts the well numbering. "
            f"Adjust the Hough parameters before trusting per-well results.")

    return positions


def well_grayscales(experiment, positions):
    """Mean grayscale of every well in every picture, shape (frames, wells)."""
    traces = []
    for img_file in experiment.img_files:
        image = cv2.imread(str(img_file))
        if image is None:
            logging.warning(f"Skipping unreadable picture {img_file}")
            continue

        if experiment.metadata.rotation is not None:
            image = cv2.rotate(image, experiment.metadata.rotation)
        if experiment.metadata.template_img is not None:
            image = auto_crop(image, experiment.metadata.template_img)

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        traces.append(circles.get_grayscales(gray, positions))

    return np.array(traces, dtype=float)


def analyse_experiment(name, positions=None, t_start=None, t_end=None,
                       robust_z=None, min_step=None, floor=None):
    """Analyse one experiment. Returns (result dict, well positions used).

    ``min_step`` may be the string 'auto' to read a threshold off this
    experiment's own data.
    """
    experiment = FrESHExperiment(name)

    if not experiment.img_files:
        raise ValueError(f"{name} has no pictures")

    if positions is None:
        positions = detect_wells(experiment)

    grayscales = well_grayscales(experiment, positions)
    frame_temps = calculate_frame_temperatures(experiment.img_files, name, floor=floor)

    suggestion, separation = suggest_min_step(grayscales)

    if min_step == 'auto':
        min_step = suggestion
        logging.info(f"{name}: min_step set to {min_step:.2f} from the data "
                     f"(the two groups of wells differ by {separation:.0f}x)")

    frames = detect_freezing_frames(grayscales, frame_temps, t_start=t_start,
                                    t_end=t_end, robust_z=robust_z,
                                    min_step=min_step)

    freezing_temps = [None if frame is None else float(frame_temps[frame])
                      for frame in frames]

    result = {
        'name': name,
        'cycle': experiment.metadata.cycle_number,
        'label': experiment.metadata.label,
        'pictures': len(experiment.img_files),
        'freezing_temps': freezing_temps,
        'frame_temperatures': frame_temps,
        'suggested_min_step': suggestion,
        'separation': separation,
        **summarise(freezing_temps),
    }
    return result, positions


def write_freezing_temps(name, freezing_temps):
    """Per-experiment freezing temperatures, next to the other interim files."""
    out_dir = paths.interim_data_path / name
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / 'freezing_temps.csv'

    with open(path, 'w', newline='') as fo:
        writer = csv.writer(fo)
        writer.writerow(['well', 'freezing_temp', 'frozen'])
        for well, temp in enumerate(freezing_temps):
            writer.writerow([well, '' if temp is None else f'{temp:.3f}',
                             int(temp is not None)])

    return path


def write_combined(results, out_path):
    """One tidy row per well per experiment."""
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, 'w', newline='') as fo:
        writer = csv.writer(fo)
        writer.writerow(COMBINED_COLUMNS)
        for result in results:
            for well, temp in enumerate(result['freezing_temps']):
                writer.writerow([result['name'],
                                 '' if result['cycle'] is None else result['cycle'],
                                 well,
                                 '' if temp is None else f'{temp:.3f}',
                                 int(temp is not None)])

    return out_path


def print_summary(results):
    """A table the operator can scan for cycles that need a second look."""
    print(f"\n{'experiment':<38} {'cyc':>4} {'pics':>5} {'frozen':>8} "
          f"{'median':>8} {'warmest':>8} {'coldest':>8}")
    print("-" * 86)

    for r in results:
        def t(key):
            return f"{r[key]:8.2f}" if r[key] is not None else f"{'-':>8}"

        cycle = r['cycle'] if r['cycle'] is not None else '-'
        frozen = f"{r['frozen']}/{r['wells']}"
        print(f"{r['name']:<38} {str(cycle):>4} {r['pictures']:>5} {frozen:>8} "
              f"{t('median_t')} {t('warmest_t')} {t('coldest_t')}")

    counts = {r['wells'] for r in results}
    if len(counts) > 1:
        print(f"\n  !! the well count differs between experiments ({sorted(counts)}); "
              f"per-well comparisons across them are not meaningful")

    suggestions = [r['suggested_min_step'] for r in results
                   if r['suggested_min_step'] is not None]
    separations = [r['separation'] for r in results]
    if suggestions:
        print(f"\n  the data suggests --min-step around "
              f"{np.median(suggestions):.1f} "
              f"(the two groups of wells differ by {np.median(separations):.0f}x)")
        if np.median(separations) < 5:
            print("  but the two groups barely separate -- either every well froze "
                  "or none did, so check a picture before trusting it")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('pattern',
                        help="experiment folders to analyse, e.g. '202609181200_WBG*'")
    parser.add_argument('--t-start', type=float, default=None,
                        help="ignore freezing warmer than this (degC)")
    parser.add_argument('--t-end', type=float, default=None,
                        help="ignore freezing colder than this (degC)")
    parser.add_argument('--robust-z', type=float, default=None,
                        help="how far a freezing step must stand out from the "
                             "well's own noise")
    parser.add_argument('--min-step', default=None,
                        help="smallest grayscale change that counts as freezing, "
                             "or 'auto' to read it off each experiment's data. "
                             "This is what separates real freezing from the "
                             "cross-talk between wells. Omit both this and "
                             "--robust-z to keep the old behaviour, where the "
                             "largest step always wins")
    parser.add_argument('--floor', type=float, default=None,
                        help="sensor temperature floor (see SENSOR_TEMPERATURE_FLOOR)")
    parser.add_argument('--redetect-wells', action='store_true',
                        help="detect the wells on every experiment instead of "
                             "reusing the first one's positions")
    parser.add_argument('-o', '--output', default=None,
                        help="combined CSV (default: data/processed/<pattern>_wells.csv)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')

    names = find_experiments(args.pattern)
    if not names:
        print(f"No experiment under {paths.raw_data_path} matches {args.pattern!r}")
        return 1

    print(f"{len(names)} experiment(s) matching {args.pattern!r}")

    min_step = args.min_step
    if min_step not in (None, 'auto'):
        try:
            min_step = float(min_step)
        except ValueError:
            print(f"--min-step must be a number or 'auto', got {min_step!r}")
            return 1

    results, positions = [], None
    for name in names:
        try:
            result, detected = analyse_experiment(
                name, positions=positions, t_start=args.t_start, t_end=args.t_end,
                robust_z=args.robust_z, min_step=min_step, floor=args.floor)
        except Exception as e:
            logging.error(f"{name}: {e}")
            continue

        if positions is None and not args.redetect_wells:
            positions = detected
            logging.info(f"Using the {len(positions)} wells found on {name} "
                         f"for the whole set")

        write_freezing_temps(name, result['freezing_temps'])
        results.append(result)

    if not results:
        print("Nothing could be analysed")
        return 1

    out_path = (paths.processed_data_path /
                f"{args.pattern.strip('*')}_wells.csv") if args.output is None \
        else paths.project_dir / args.output
    write_combined(results, out_path)

    print_summary(results)
    print(f"\nCombined table: {out_path}")
    print(f"Plot it with:   python -m src.analysis.figures {out_path}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
