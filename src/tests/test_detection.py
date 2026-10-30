"""Freezing detection (src/analysis/detection.py)."""

import numpy as np
import pytest

from src.analysis.detection import (detect_freezing_frames, frame_window,
                                    frozen_fraction, robust_sigma, summarise)

N_FRAMES = 60


def well(freezes_at=None, noise=0.5, step=40.0, seed=0):
    """One well's grayscale history: flat, plus a step if it freezes."""
    rng = np.random.default_rng(seed)
    trace = 100 + rng.normal(0, noise, N_FRAMES)
    if freezes_at is not None:
        trace[freezes_at:] += step
    return trace


def plate(*wells):
    return np.column_stack(wells)


def temperatures(start=0.0, end=-30.0):
    """A cooling ramp, one temperature per frame."""
    return np.linspace(start, end, N_FRAMES)


# -- the basics -------------------------------------------------------------

def test_a_clear_step_is_found():
    frames = detect_freezing_frames(plate(well(freezes_at=30)))

    assert frames == [30]


def test_every_well_is_reported_independently():
    frames = detect_freezing_frames(plate(well(freezes_at=10, seed=1),
                                          well(freezes_at=40, seed=2)))

    assert frames == [10, 40]


def test_a_well_that_never_freezes_comes_back_as_none():
    """Regression: argmax always returns something, so every well used to be
    declared frozen -- which makes a water background read as fully frozen."""
    frames = detect_freezing_frames(plate(well(freezes_at=None)))

    assert frames == [None]


def test_a_water_background_keeps_its_unfrozen_wells():
    wells = [well(freezes_at=None, seed=i) for i in range(90)]
    wells += [well(freezes_at=45, seed=100 + i) for i in range(6)]

    frames = detect_freezing_frames(plate(*wells))

    assert sum(f is not None for f in frames) == 6
    assert frames[-6:] == [45] * 6


def test_without_a_threshold_the_old_behaviour_is_kept():
    """So the existing analysis window is unaffected."""
    frames = detect_freezing_frames(plate(well(freezes_at=None)), robust_z=None)

    assert frames[0] is not None


def test_a_noisy_well_needs_a_bigger_step():
    """The threshold is per well, against that well's own noise."""
    quiet = detect_freezing_frames(plate(well(freezes_at=30, noise=0.5, step=8)))
    noisy = detect_freezing_frames(plate(well(freezes_at=30, noise=6.0, step=8)))

    assert quiet == [30]
    assert noisy == [None]


# -- the temperature window -------------------------------------------------

def test_a_spurious_early_event_is_excluded_by_the_window():
    """Freezing detected while the plate is still warm is usually not real."""
    trace = well(freezes_at=None, seed=3)
    trace[5:] += 60      # a flicker at -2.5 degC
    trace[40:] += 40     # the real event, colder

    everything = detect_freezing_frames(plate(trace))
    windowed = detect_freezing_frames(plate(trace), temperatures(),
                                      t_start=-5.0)

    assert everything == [5], "without a window the flicker wins"
    assert windowed == [40]


def test_the_cold_end_can_be_excluded_too():
    trace = well(freezes_at=None, seed=4)
    trace[55:] += 60     # a disturbance right at the end

    assert detect_freezing_frames(plate(trace)) == [55]
    assert detect_freezing_frames(plate(trace), temperatures(), t_end=-25.0) == [None]


def test_a_window_with_no_frames_detects_nothing(caplog):
    frames = detect_freezing_frames(plate(well(freezes_at=30)), temperatures(),
                                    t_start=-50.0)

    assert frames == [None]
    assert 'No frame lies between' in caplog.text


@pytest.mark.parametrize('t_start, t_end, expected', [
    (None, None, 5), (-2.0, None, 4), (None, -6.0, 4), (-2.0, -6.0, 3),
])
def test_the_window_mask(t_start, t_end, expected):
    assert frame_window([0.0, -2.0, -4.0, -6.0, -8.0], t_start, t_end).sum() == expected


# -- frozen fraction --------------------------------------------------------

def test_unfrozen_wells_stay_in_the_denominator():
    """A background that mostly does not freeze must not read as ff = 1."""
    temps = [-5.0, -10.0, -15.0]

    ff = frozen_fraction([-8.0, -12.0, None, None], temps)

    assert list(ff) == [0.0, 0.25, 0.5]


def test_frozen_fraction_of_a_plate_that_all_froze():
    ff = frozen_fraction([-8.0, -9.0], [-5.0, -20.0])

    assert list(ff) == [0.0, 1.0]


# -- odds and ends ----------------------------------------------------------

def test_robust_sigma_ignores_one_big_step():
    quiet = np.array([0.1, -0.2, 0.15, -0.1, 0.05])
    with_step = np.append(quiet, 50.0)

    assert robust_sigma(with_step) == pytest.approx(robust_sigma(quiet), rel=0.5)


def test_the_summary_counts_both_kinds_of_well():
    assert summarise([-8.0, -12.0, None]) == {
        'wells': 3, 'frozen': 2, 'unfrozen': 1,
        'median_t': -10.0, 'warmest_t': -8.0, 'coldest_t': -12.0}


def test_the_summary_of_a_plate_that_never_froze():
    assert summarise([None, None])['median_t'] is None


def test_a_single_picture_cannot_show_freezing(caplog):
    assert detect_freezing_frames(np.zeros((1, 4))) == [None] * 4
    assert 'Not enough pictures' in caplog.text


def test_a_wrong_shape_is_rejected():
    with pytest.raises(ValueError, match='n_frames, n_wells'):
        detect_freezing_frames(np.zeros(10))


# -- artefacts that hit the whole plate at once ------------------------------

#: Wells 0-9 really freeze, one per frame from 35 on -- stochastic, as real
#: freezing is. Wells 10-19 never do. The artefact at frame 8 hits all of them
#: and is bigger than any real step, so without the check it wins everywhere.
ARTEFACT_FRAME = 8
REAL_FREEZES = {i: 35 + i for i in range(10)}


def plate_with_artefact(n_wells=20):
    wells = []
    for i in range(n_wells):
        trace = well(freezes_at=None, noise=0.3, seed=i)
        if i in REAL_FREEZES:
            trace[REAL_FREEZES[i]:] += 25
        trace[ARTEFACT_FRAME:] += 60       # the whole plate jumps at once
        wells.append(trace)
    return plate(*wells)


def test_without_the_check_the_artefact_is_read_as_freezing():
    frames = detect_freezing_frames(plate_with_artefact(), min_step=10)

    assert frames.count(ARTEFACT_FRAME) == 20, "the artefact should win everywhere"


def test_a_frame_the_whole_plate_shares_is_rejected(caplog):
    """Freezing is stochastic well by well; twenty at one instant is the picture."""
    frames = detect_freezing_frames(plate_with_artefact(), min_step=10,
                                    max_simultaneous=0.25)

    assert ARTEFACT_FRAME not in frames
    assert 'picture artefact' in caplog.text


def test_the_wells_that_really_froze_are_found_at_their_real_frame():
    """The point of looking again: a well that froze later is not lost."""
    frames = detect_freezing_frames(plate_with_artefact(), min_step=10,
                                    max_simultaneous=0.25)

    assert frames[:10] == list(REAL_FREEZES.values()), \
        "the real, later freezing was not recovered"
    assert frames[10:] == [None] * 10, "the rest never froze"


def test_genuine_clustering_is_left_alone():
    """Many wells really do freeze within one frame where the bulk goes."""
    wells = [well(freezes_at=30, noise=0.3, seed=i) for i in range(8)]
    wells += [well(freezes_at=None, noise=0.3, seed=100 + i) for i in range(92)]

    frames = detect_freezing_frames(plate(*wells), min_step=10,
                                    max_simultaneous=0.25)

    assert frames[:8] == [30] * 8, "8 of 100 wells is not an artefact"


def test_several_artefact_frames_are_all_rejected():
    wells = []
    for i in range(20):
        trace = well(freezes_at=None, noise=0.3, seed=i)
        trace[8:] += 30       # first light change
        trace[20:] += 25      # second one
        wells.append(trace)

    frames = detect_freezing_frames(plate(*wells), min_step=10, max_simultaneous=0.25)

    assert frames == [None] * 20


def test_the_largest_group_is_reported():
    from src.analysis.detection import largest_simultaneous_group

    assert largest_simultaneous_group([5, 5, 5, 9, None]) == (5, 3)
    assert largest_simultaneous_group([None, None]) == (None, 0)
