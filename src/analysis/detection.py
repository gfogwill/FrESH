"""Finding the frame at which each well froze.

The freezing of a well shows up as a step in its mean grayscale: the drop goes
from clear to opaque between one picture and the next. The old detection took
``argmax(|diff|)`` over the whole series, which has two consequences:

* ``argmax`` always returns something, so **every** well was declared frozen.
  For a filter sample where all 96 freeze that is harmless. For a water
  background, where most wells never freeze in the scanned range, it invents a
  freezing temperature for every one of them and the frozen fraction runs up
  to 1.0 regardless.
* It searches the whole scan, so a flicker while the plate is still warm, or a
  disturbance at the very end, wins over the real event.

Here a well counts as frozen only when its largest step stands out from that
well's *own* frame-to-frame noise, and only inside a temperature window the
operator can set. Wells that never freeze come back as ``None``: right-censored,
which is what they are.
"""

import logging

import numpy as np

#: How far the freezing step must stand out from a well's own noise, in robust
#: standard deviations. Tune it on real images; 5 is a starting point.
DEFAULT_ROBUST_Z = 5.0

#: A statistical threshold alone is not enough. ``get_grayscales`` subtracts the
#: mean of the whole picture from every well, so each time ONE well freezes the
#: mean shifts and every OTHER well takes a small step in sympathy. That step is
#: tiny in absolute terms but large compared with a well's own noise -- on
#: synthetic plates it measures around 30 sigma -- so it sails through any
#: z-score test. Freezing is also a large ABSOLUTE change in brightness, and
#: min_step is what separates the two. suggest_min_step() reads a value off the
#: data.

#: Scale factor making the median absolute deviation comparable to a standard
#: deviation for normally distributed noise.
MAD_TO_SIGMA = 1.4826


def robust_sigma(values):
    """A standard deviation that a single large step cannot inflate."""
    values = np.asarray(values, dtype=float)
    if values.size == 0:
        return 0.0

    mad = np.median(np.abs(values - np.median(values)))
    return float(MAD_TO_SIGMA * mad)


def frame_window(frame_temperatures, t_start=None, t_end=None):
    """Frames whose temperature lies inside the valid window.

    ``t_start`` is the warm end (ignore anything warmer) and ``t_end`` the cold
    end (ignore anything colder). Either may be None. Returns a boolean mask.
    """
    temperatures = np.asarray(frame_temperatures, dtype=float)
    mask = np.ones(temperatures.shape, dtype=bool)

    if t_start is not None:
        mask &= temperatures <= t_start
    if t_end is not None:
        mask &= temperatures >= t_end

    return mask


def simultaneous_groups(freezing_frames):
    """How many wells were assigned to each frame."""
    from collections import Counter
    return Counter(f for f in freezing_frames if f is not None)


def largest_simultaneous_group(freezing_frames):
    """(frame, count) of the frame that most wells were assigned to."""
    groups = simultaneous_groups(freezing_frames)
    if not groups:
        return None, 0

    frame, count = groups.most_common(1)[0]
    return frame, count


def suggest_min_step(grayscales):
    """A min_step read off the data, by finding the gap between the two groups.

    Wells that froze show a step of tens of grayscale levels; wells that did not
    show a fraction of one. Sorting the per-well largest steps and cutting at
    the widest ratio between neighbours lands between the groups.

    Returns (suggestion, separation). A separation near 1 means there is no gap
    -- either every well froze or none did -- and the suggestion is meaningless.
    """
    grayscales = np.asarray(grayscales, dtype=float)
    if grayscales.shape[0] < 2:
        return None, 1.0

    steps = np.sort(np.abs(np.diff(grayscales, axis=0)).max(axis=0))
    steps = steps[steps > 0]
    if steps.size < 2:
        return None, 1.0

    ratios = steps[1:] / steps[:-1]
    cut = int(np.argmax(ratios))

    return float(np.sqrt(steps[cut] * steps[cut + 1])), float(ratios[cut])


def detect_freezing_frames(grayscales, frame_temperatures=None,
                           t_start=None, t_end=None, robust_z=DEFAULT_ROBUST_Z,
                           min_step=None, max_simultaneous=None):
    """Return the frame index at which each well froze, or None where it did not.

    Parameters
    ----------
    grayscales : array, shape (n_frames, n_wells)
        Mean grayscale of every well in every picture.
    frame_temperatures : sequence of float, optional
        Temperature of each frame; required to use ``t_start``/``t_end``.
    t_start, t_end : float, optional
        Only look for freezing between these temperatures.
    robust_z : float, optional
        How far the step must stand out from the well's own noise. Pass None to
        skip the statistical test.
    min_step : float, optional
        Smallest change in grayscale that counts as freezing. This is the test
        that rejects the cross-talk between wells; see the note on min_step
        above. Pass None to skip it.

        With both set to None the largest step always wins, which is what the
        analysis window has always done.
    max_simultaneous : float, optional
        Largest share of the plate allowed to freeze in one frame, e.g. 0.25.
        Freezing is stochastic well by well, so a frame that dozens of wells
        share is an artefact of the picture -- the light changed, the camera
        re-exposed, somebody knocked the bench -- not forty wells freezing at
        once. Such a frame is blanked and the wells that were on it are looked
        at again, so a well that really froze later is found at its real
        temperature instead of being lost.

    Returns
    -------
    list
        One entry per well: the frame index, or None if the well never froze.
    """
    grayscales = np.asarray(grayscales, dtype=float)
    if grayscales.ndim != 2:
        raise ValueError(f"expected (n_frames, n_wells), got {grayscales.shape}")

    n_frames, n_wells = grayscales.shape
    if n_frames < 2:
        logging.warning("Not enough pictures to detect any freezing")
        return [None] * n_wells

    # diffs[k] is the step between frame k and frame k+1, so a step at diffs[k]
    # means the well is frozen from frame k+1 onwards.
    diffs = np.diff(grayscales, axis=0)

    if frame_temperatures is None:
        allowed = np.ones(n_frames, dtype=bool)
    else:
        allowed = frame_window(frame_temperatures, t_start, t_end)
        if not allowed.any():
            logging.warning(f"No frame lies between {t_start} and {t_end} degC; "
                            f"no freezing can be detected")
            return [None] * n_wells

    # A step counts only when the frame it lands on is inside the window.
    usable = allowed[1:]

    # A well is judged against its own noise, but a well whose noise estimate
    # comes out degenerate (a perfectly flat trace) would otherwise make every
    # flicker infinitely significant. Fall back to the noise of the plate.
    sigmas = np.array([robust_sigma(diffs[usable, well]) for well in range(n_wells)])
    plate_sigma = float(np.median(sigmas[sigmas > 0])) if (sigmas > 0).any() else 0.0

    if robust_z is not None and plate_sigma <= 0:
        logging.warning("Every well has a perfectly flat trace; the freezing "
                        "threshold falls back to the size of the steps themselves")

    freezing_frames = []
    for well in range(n_wells):
        well_diffs = diffs[:, well]
        magnitudes = np.abs(well_diffs)

        candidates = np.where(usable, magnitudes, -np.inf)
        if not np.isfinite(candidates).any():
            freezing_frames.append(None)
            continue

        best = int(np.argmax(candidates))

        if min_step is not None and magnitudes[best] < min_step:
            freezing_frames.append(None)   # too small to be a freezing event
            continue

        if robust_z is not None and not _is_a_step(magnitudes[best], sigmas[well],
                                                   plate_sigma, magnitudes[usable],
                                                   robust_z):
            freezing_frames.append(None)   # lost in this well's own noise
            continue

        freezing_frames.append(best + 1)

    if max_simultaneous is not None:
        freezing_frames = _reject_simultaneous(
            freezing_frames, diffs, usable, sigmas, plate_sigma,
            robust_z, min_step, max_simultaneous)

    return freezing_frames


def _reject_simultaneous(freezing_frames, diffs, usable, sigmas, plate_sigma,
                         robust_z, min_step, max_simultaneous):
    """Blank the frames too many wells share, and look at those wells again."""
    n_wells = len(freezing_frames)
    limit = max(2, int(round(max_simultaneous * n_wells)))
    blanked = np.zeros(diffs.shape[0], dtype=bool)

    # Rejecting one frame can expose another, so keep going until it settles.
    for _ in range(n_wells):
        frame, count = largest_simultaneous_group(freezing_frames)
        if frame is None or count < limit:
            break

        logging.warning(f"{count} of {n_wells} wells were assigned to one frame; "
                        f"treating it as a picture artefact, not as {count} wells "
                        f"freezing at the same instant")
        blanked[frame - 1] = True
        allowed = usable & ~blanked

        for well in range(n_wells):
            if freezing_frames[well] != frame:
                continue

            magnitudes = np.abs(diffs[:, well])
            candidates = np.where(allowed, magnitudes, -np.inf)

            if not np.isfinite(candidates).any():
                freezing_frames[well] = None
                continue

            best = int(np.argmax(candidates))

            if min_step is not None and magnitudes[best] < min_step:
                freezing_frames[well] = None
            elif robust_z is not None and not _is_a_step(
                    magnitudes[best], sigmas[well], plate_sigma,
                    magnitudes[allowed], robust_z):
                freezing_frames[well] = None
            else:
                freezing_frames[well] = best + 1

    return freezing_frames


def _is_a_step(magnitude, well_sigma, plate_sigma, well_magnitudes, robust_z):
    """Does the largest change in a well stand out enough to be freezing?"""
    sigma = max(well_sigma, plate_sigma)

    if sigma > 0:
        return magnitude >= robust_z * sigma

    # No usable noise anywhere: fall back to comparing the step against the
    # rest of that well's own changes, which is the only scale left.
    others = np.sort(well_magnitudes)[:-1]
    baseline = float(np.max(others)) if others.size else 0.0

    return magnitude > max(baseline * robust_z, np.finfo(float).eps)


def frozen_fraction(freezing_temperatures, temperatures):
    """Fraction of wells frozen at each temperature, counting censored wells.

    A well that never froze still counts in the denominator -- that is the
    whole point of a background measurement.
    """
    frozen = np.asarray([t for t in freezing_temperatures if t is not None], dtype=float)
    total = len(freezing_temperatures)

    if total == 0:
        return np.zeros(len(temperatures))

    # Cooling, so a well is frozen once the plate is at or below its own
    # freezing temperature.
    return np.array([(frozen >= t).sum() / total for t in temperatures], dtype=float)


def summarise(freezing_temperatures):
    """A few numbers describing one plate, for the batch summary table."""
    frozen = [t for t in freezing_temperatures if t is not None]
    total = len(freezing_temperatures)

    return {
        'wells': total,
        'frozen': len(frozen),
        'unfrozen': total - len(frozen),
        'median_t': float(np.median(frozen)) if frozen else None,
        'warmest_t': max(frozen) if frozen else None,
        'coldest_t': min(frozen) if frozen else None,
    }
