#!/usr/bin/env python3
"""The refreeze figure, from the table :mod:`src.analysis.batch` writes.

    python -m src.analysis.figures data/processed/<name>_wells.csv

Three panels:

1. the spectrum of every cycle, coloured by cycle number;
2. how far each cycle sits from the series median, in decades;
3. how much consecutive cycles differ.

Cycle number is a *sequential* quantity, so the cycles are coloured with a
sequential, colourblind-safe ramp and identified by a colour bar rather than by
a legend with fifty entries.
"""

import argparse
import csv
import logging
import sys
import warnings
from collections import defaultdict

import numpy as np

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

#: Perceptually uniform and colourblind-safe; the standard for sequential
#: scientific data.
CYCLE_CMAP = 'viridis'

#: Default drop volume [mL] if the table does not come with one.
DEFAULT_V_DROP = 5e-05

GRID = dict(alpha=0.3, linewidth=0.5)


def read_wells(path):
    """Read the batch table into {cycle: [freezing temperatures]}."""
    by_cycle = defaultdict(list)

    with open(path, newline='') as fo:
        for row in csv.DictReader(fo):
            key = row.get('cycle') or row.get('experiment')
            try:
                key = int(key)
            except (TypeError, ValueError):
                pass

            temp = row.get('freezing_temp', '').strip()
            by_cycle[key].append(float(temp) if temp else None)

    return dict(by_cycle)


def frozen_fraction_curve(freezing_temps, grid):
    """Cumulative frozen fraction on a temperature grid.

    Wells that never froze stay in the denominator, which is the whole point of
    a background measurement.
    """
    frozen = np.array([t for t in freezing_temps if t is not None], dtype=float)
    total = len(freezing_temps)
    if total == 0:
        return np.zeros_like(grid)

    return np.array([(frozen >= t).sum() / total for t in grid])


def cumulative_concentration(ff, v_drop):
    """Vali's K(T): nuclei per mL of suspension, from the frozen fraction.

    ff = 1 would be infinite, so the top well is left out rather than clipped
    to an arbitrary number.
    """
    with np.errstate(divide='ignore', invalid='ignore'):
        k = -np.log(1.0 - ff) / v_drop

    k[~np.isfinite(k)] = np.nan
    k[ff <= 0] = np.nan
    return k


def build_curves(by_cycle, v_drop, n_points=200):
    """A common temperature grid and one spectrum per cycle."""
    all_temps = [t for temps in by_cycle.values() for t in temps if t is not None]
    if not all_temps:
        raise ValueError("no well froze anywhere in this table")

    grid = np.linspace(max(all_temps), min(all_temps), n_points)

    curves = {}
    for cycle in sorted(by_cycle, key=lambda c: (isinstance(c, str), c)):
        ff = frozen_fraction_curve(by_cycle[cycle], grid)
        curves[cycle] = {'ff': ff, 'k': cumulative_concentration(ff, v_drop)}

    return grid, curves


def drift(curves):
    """How far each cycle sits from the series median, in decades.

    A cycle where nothing froze is all NaN, and so is the warm end of every
    spectrum, so empty slices are expected rather than a problem.
    """
    stack = np.array([np.log10(c['k']) for c in curves.values()])

    with warnings.catch_warnings(), np.errstate(invalid='ignore'):
        warnings.simplefilter('ignore', RuntimeWarning)
        median = np.nanmedian(stack, axis=0)
        return np.nanmedian(stack - median, axis=1)


def consecutive_differences(curves):
    """Every point-by-point difference between one cycle and the next, in decades."""
    stack = np.array([np.log10(c['k']) for c in curves.values()])
    if stack.shape[0] < 2:
        return np.array([])

    diffs = np.diff(stack, axis=0).ravel()
    return diffs[np.isfinite(diffs)]


def plot(grid, curves, quantity='k', title=None, units='mL$^{-1}$'):
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.4))
    cycles = list(curves)
    numeric = [c for c in cycles if isinstance(c, (int, float))]

    cmap = plt.get_cmap(CYCLE_CMAP)
    lo, hi = (min(numeric), max(numeric)) if numeric else (0, 1)
    norm = matplotlib.colors.Normalize(vmin=lo, vmax=max(hi, lo + 1))

    # 1 -- every cycle's spectrum
    ax = axes[0]
    for cycle, curve in curves.items():
        colour = cmap(norm(cycle)) if isinstance(cycle, (int, float)) else 'grey'
        ax.plot(grid, curve[quantity], color=colour, linewidth=1)

    if quantity == 'k':
        ax.set_yscale('log')
        ax.set_ylabel(f'$N_{{INP}}$ [{units}]')
    else:
        ax.set_ylabel('frozen fraction')

    ax.set_xlabel('temperature [°C]')
    ax.set_title(f'{len(cycles)} consecutive freeze/thaw cycles')
    ax.grid(**GRID)

    if numeric:
        bar = fig.colorbar(matplotlib.cm.ScalarMappable(norm=norm, cmap=cmap), ax=ax)
        bar.set_label('cycle number')
        bar.locator = matplotlib.ticker.MaxNLocator(integer=True)
        bar.update_ticks()

    # 2 -- drift across the series
    ax = axes[1]
    deltas = drift(curves)
    ax.plot(cycles, deltas, 'o-', markersize=5, linewidth=1)
    ax.axhline(0, color='black', linestyle=':', linewidth=1)
    for limit in (-0.3, 0.3):
        ax.axhline(limit, color='grey', linestyle='--', linewidth=0.8)
    ax.set_xlabel('cycle number')
    ax.set_ylabel(r'$\delta$ [decades] vs the series median')
    ax.set_title('Drift across the series')
    ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))

    # Keep the +/-0.3 reference lines in view, but never crop a real point out
    # of the panel: a series that drifts further is exactly what this is for.
    finite = deltas[np.isfinite(deltas)]
    reach = max(0.35, float(np.max(np.abs(finite))) * 1.15) if finite.size else 0.35
    ax.set_ylim(-reach, reach)
    ax.grid(**GRID)

    # 3 -- how much consecutive cycles differ
    ax = axes[2]
    diffs = consecutive_differences(curves)
    if diffs.size:
        ax.hist(diffs, bins=40)
        ax.set_title('Cycle-to-cycle difference\n'
                     f'median |d| = {np.median(np.abs(diffs)):.3f} decades')
    else:
        ax.set_title('Cycle-to-cycle difference\n(needs at least two cycles)')

    ax.axvline(0, color='black', linestyle=':', linewidth=1)
    for limit in (-0.3, 0.3):
        ax.axvline(limit, color='grey', linestyle='--', linewidth=0.8)
    ax.set_xlabel(r'$\delta$ [decades]  (consecutive cycles)')
    ax.set_ylabel('count')
    ax.grid(**GRID)

    if title:
        fig.suptitle(title)

    fig.tight_layout()
    return fig


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('table', help="the CSV written by src.analysis.batch")
    parser.add_argument('-o', '--output', default=None, help="PNG to write")
    parser.add_argument('--v-drop', type=float, default=DEFAULT_V_DROP,
                        help="drop volume in mL")
    parser.add_argument('--quantity', choices=('k', 'ff'), default='k',
                        help="cumulative concentration, or frozen fraction")
    parser.add_argument('--title', default=None)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')

    by_cycle = read_wells(args.table)
    if not by_cycle:
        print(f"{args.table} has no rows")
        return 1

    grid, curves = build_curves(by_cycle, args.v_drop)

    frozen = {c: sum(t is not None for t in temps) for c, temps in by_cycle.items()}
    print(f"{len(curves)} cycle(s); wells frozen per cycle: "
          f"{', '.join(f'{c}:{n}' for c, n in frozen.items())}")

    fig = plot(grid, curves, quantity=args.quantity, title=args.title)

    out = args.output or str(args.table).rsplit('.', 1)[0] + '.png'
    fig.savefig(out, dpi=140)
    print(f"Figure: {out}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
