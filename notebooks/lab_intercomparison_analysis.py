#!/usr/bin/env python3
"""
lab_intercomparison_analysis.py

Pipeline:
  1. Configuration
  2. Calibration loading
  3. Data loading helpers
  4. Frozen fraction + Agresti-Coull CI
  5. Binned spectra (Vali 2019) + background correction
  6. Main loop: load, calibrate, compute
  7. Plots: FF grid, K(T) grid, T50 vs dilution, grouped binned
  8. CSV export (organizer format)
"""

from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import math
from src import paths

# ─────────────────────────────────────────────────────────────────────
# 1. CONFIGURATION
# ─────────────────────────────────────────────────────────────────────

interim_dir = paths.interim_data_path
output_dir  = paths.reports_path / "lab_intercomparison"
output_dir.mkdir(exist_ok=True)

V_drop_L  = 50e-6   # drop volume in litres (50 µL)
V_drop_mL = V_drop_L * 1000   # 0.05 mL
CI_Z      = 1.96    # z for 95% Agresti-Coull CI

BIN_DT  = 0.5
T_BINS  = np.arange(0.0, -35.0, -BIN_DT)           # bin centers (°C)
T_EDGES = np.append(T_BINS + BIN_DT / 2,              # warm edge de cada bin
                    T_BINS[-1] - BIN_DT / 2)        # warm → cold edges
T_BINS_K = T_BINS + 273.15                    # bin centers (K)

experiments = [
    "202604101455_KIT_SUSPENSION_D1_RE1050_B_RUN1",
    "202604101455_KIT_SUSPENSION_D1_RE1050_B_RUN0",
    "202604101455_KIT_SUSPENSION_D1_RE1050_A_RUN1",
    "202604101455_KIT_SUSPENSION_D1_RE1050_A_RUN0",
    "202604101454_KIT_SUSPENSION_D1_RP1845_B_RUN1",
    "202604101454_KIT_SUSPENSION_D1_RP1845_B_RUN0",
    "202604101454_KIT_SUSPENSION_D1_RP1845_A_RUN1",
    "202604101454_KIT_SUSPENSION_D1_RP1845_A_RUN0",
    "202604101702_KIT_SUSPENSION_D10_RP1845_B_RUN1",
    "202604101702_KIT_SUSPENSION_D10_RP1845_A_RUN1",
    "202604101633_KIT_SUSPENSION_D10_RE1050_B_RUN0",
    "202604101633_KIT_SUSPENSION_D10_RE1050_A_RUN0",
    "202604101700_KIT_SUSPENSION_D10_RE1050_B_RUN1",
    "202604101700_KIT_SUSPENSION_D10_RE1050_A_RUN1",
    "202604101632_KIT_SUSPENSION_D10_RP1845_B_RUN0",
    "202604101632_KIT_SUSPENSION_D10_RP1845_A_RUN0",
    "202604101731_KIT_SUSPENSION_D100_RE1050_A_RUN0",
    "202604101731_KIT_SUSPENSION_D100_RE1050_B_RUN0",
    "202604101738_KIT_SUSPENSION_D100_RP1845_A_RUN0",
    "202604101738_KIT_SUSPENSION_D100_RP1845_B_RUN0",
    "202604101354_KIT_NPFILTERED-WATER_D0_RE1050_B_RUN0",
    "202604101354_KIT_NPFILTERED-WATER_D0_RE1050_A_RUN0",
    "202604101353_KIT_NPWATER-FILTERED_D0_RP1845_B_RUN0",
    "202604101353_KIT_NPWATER-FILTERED_D0_RP1845_A_RUN0",
]

CALIBRATION_CSV = Path(
    "/home/perezfo/PycharmProjects/FrESH_characterization/output/all_characterization_models.csv"
)

dilution_factor_map = {"D0": 1, "D1": 1, "D10": 10, "D100": 100}

background_map = {
    "RE1050": "202604101354_KIT_NPFILTERED-WATER_D0_RE1050",
    "RP1845": "202604101353_KIT_NPWATER-FILTERED_D0_RP1845",
}

color_map     = {"D0": "#d62728", "D1": "#1f77b4", "D10": "#ff7f0e", "D100": "#2ca02c"}
linestyle_map = {"A": "-", "B": "--"}
marker_map    = {"RUN0": "o", "RUN1": "s"}

DILUTIONS_ORDERED = ["D1", "D10", "D100"]
CHILLERS          = ["RE1050", "RP1845"]

color_map = {
    "D1":   "#0072B2",   # blue
    "D10":  "#D55E00",   # vermillion
    "D100": "#009E73",   # bluish green
}
style_map = {
    "RE1050": {"ls": "-",  "lw": 2.2, "alpha": 0.95},
    "RP1845": {"ls": "--", "lw": 2.2, "alpha": 0.95},
    "CS":     {"ls": "-",  "lw": 1.8, "alpha": 0.95, "marker": "o", "ms": 3},
}
uncorr_style = {"lw": 1.0, "alpha": 0.20}

# ─────────────────────────────────────────────────────────────────────
# 2. CALIBRATION
# ─────────────────────────────────────────────────────────────────────

_cal_df = pd.read_csv(CALIBRATION_CSV)
_cal_stats = (
    _cal_df.groupby("chiller")
    .agg(
        a_mean=("a_slope",     "mean"),
        a_std= ("a_slope",     "std"),
        b_mean=("b_intercept", "mean"),
        b_std= ("b_intercept", "std"),
    )
)


def calibration_params(chiller):
    if chiller not in _cal_stats.index:
        raise KeyError(f"Chiller '{chiller}' not found in calibration CSV.")
    row = _cal_stats.loc[chiller]
    return row.a_mean, row.b_mean, row.a_std, row.b_std


def sigma_T_at_bin(T_bin_C, chiller):
    """Temperature uncertainty at a bin center propagated from calibration."""
    _, _, sa, sb = calibration_params(chiller)
    return float(np.sqrt((T_bin_C * sa) ** 2 + sb ** 2))


# ─────────────────────────────────────────────────────────────────────
# 3. DATA LOADING + CALIBRATION
# ─────────────────────────────────────────────────────────────────────

def parse_name(exp):
    parts = exp.split("_", 1)[1].split("_")
    return {
        "experiment": exp,
        "dilution":   parts[2],
        "condition":  parts[3],
        "plate":      parts[4],
        "run":        parts[5],
    }


def load_and_calibrate(interim_dir, exp, chiller):
    csv_path = interim_dir / exp / "freezing_temps.csv"
    df = pd.read_csv(csv_path)
    if "excluded" in df.columns:
        df = df.loc[~df["excluded"].fillna(False).astype(bool)].copy()
    df["Temperature"] = pd.to_numeric(df["Temperature"], errors="coerce")
    df = df.dropna(subset=["Temperature"]).copy()
    a, b, sa, sb = calibration_params(chiller)
    T_raw = df["Temperature"].values
    df["T_cal"]   = a * T_raw + b
    df["T_sigma"] = np.sqrt((T_raw * sa) ** 2 + sb ** 2)
    return df


# ─────────────────────────────────────────────────────────────────────
# 4. FROZEN FRACTION + AGRESTI-COULL CI
# ─────────────────────────────────────────────────────────────────────

def frozen_fraction_with_ci(T_freeze, z=CI_Z):
    """
    Cumulative frozen fraction curve with Agresti-Coull 95% CI.
    Returns (temps, ff, ff_lo, ff_hi) sorted warm → cold.
    """
    temps    = np.sort(T_freeze)[::-1]
    N        = len(temps)
    n_frozen = np.arange(1, N + 1)
    n_tilde  = n_frozen + z ** 2 / 2
    N_tilde  = N + z ** 2
    p_tilde  = n_tilde / N_tilde
    margin   = z * np.sqrt(p_tilde * (1 - p_tilde) / N_tilde)
    ff       = n_frozen / N
    ff_lo    = np.clip(p_tilde - margin, 0, 1)
    ff_hi    = np.clip(p_tilde + margin, 0, 1)
    return temps, ff, ff_lo, ff_hi


def KT_from_ff(ff, V_drop, dilution_factor=1.0):
    f = np.clip(ff, 1e-9, 1 - 1e-9)
    return -np.log(1 - f) / V_drop * dilution_factor


def KT_uncertainty(ff, ff_lo, ff_hi, V_drop, dilution_factor=1.0):
    K    = KT_from_ff(ff,    V_drop, dilution_factor)
    K_lo = KT_from_ff(ff_lo, V_drop, dilution_factor)
    K_hi = KT_from_ff(ff_hi, V_drop, dilution_factor)
    return K, K_lo, K_hi


# ─────────────────────────────────────────────────────────────────────
# 5. BINNED SPECTRA + BACKGROUND CORRECTION
# ─────────────────────────────────────────────────────────────────────

def compute_binned_spectra(T_freeze, V_drop, dilution_factor=1.0,
                           t_edges=T_EDGES, t_bins=T_BINS, dT=BIN_DT, trim_endpoints=True):
    """
    Differential k(T) and cumulative K(T) on fixed bin grid (Vali 2019, Eq.1).

    Returns
    -------
    t_bins     : bin centers (°C)
    N_bin      : events per bin
    N_unfrozen : wells unfrozen at start of each bin
    k_T        : differential spectrum [INP V_drop_unit⁻¹ °C⁻¹]
    K_T        : cumulative spectrum   [INP V_drop_unit⁻¹]
    valid_mask : boolean mask — bins with at least one event (no plateau)
    """
    N_total     = len(T_freeze)
    N_bin       = np.zeros(len(t_bins))
    for i, (T_hi, T_lo) in enumerate(zip(t_edges[:-1], t_edges[1:])):
        N_bin[i] = np.sum((T_freeze <= T_hi) & (T_freeze > T_lo))

    N_cumfrozen = np.cumsum(N_bin)
    N_unfrozen  = N_total - np.concatenate([[0], N_cumfrozen[:-1]])

    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(N_unfrozen > 0, N_bin / N_unfrozen, 0.0)
        k_T   = np.where(
            N_unfrozen > 0,
            -np.log(1 - np.clip(ratio, 0, 1 - 1e-9)) / V_drop / dT,
            0.0,
        )

    K_T = np.cumsum(k_T * dT) * dilution_factor
    k_T = k_T * dilution_factor

    # valid range: from first to last bin that had actual freezing events
    active = np.where(N_bin > 0)[0]
    valid_mask = np.zeros(len(t_bins), dtype=bool)

    if len(active) == 0:
        pass
    elif len(active) == 1:
        # solo un bin: nada que mostrar (ambos extremos son el mismo)
        pass
    elif trim_endpoints:
        # excluir primer y último bin activo
        valid_mask[active[0] + 1 : active[-1]] = True
    else:
        valid_mask[active[0] : active[-1] + 1] = True

    return t_bins, N_bin, N_unfrozen, k_T, K_T, valid_mask


def background_correct_binned(k_T_sample, k_T_bg, dT=BIN_DT):
    k_corrected = np.maximum(k_T_sample - k_T_bg, 0.0)
    K_corrected = np.cumsum(k_corrected * dT)
    return k_corrected, K_corrected


# ─────────────────────────────────────────────────────────────────────
# 6. SUMMARY HELPERS
# ─────────────────────────────────────────────────────────────────────

def temp_at_ff(temps, ff, target):
    if target < ff.min() or target > ff.max():
        return np.nan
    idx = np.clip(np.searchsorted(ff, target), 0, len(ff) - 1)
    return float(temps[idx])


def dilution_to_numeric(dil):
    return float(dil[1:]) if dil.startswith("D") and dil[1:].isdigit() else np.nan


# ─────────────────────────────────────────────────────────────────────
# 7. MAIN DATA LOOP
# ─────────────────────────────────────────────────────────────────────

# Pre-compute background k(T) per chiller (pooled over A/B replicates)
bg_kT = {}
for cond, bg_exp_base in background_map.items():
    bg_temps_all = []
    for exp in experiments:
        if bg_exp_base in exp:
            try:
                df_bg = load_and_calibrate(interim_dir, exp, cond)
                bg_temps_all.extend(df_bg["T_cal"].values)
            except Exception:
                pass
    if bg_temps_all:
        _, _, _, k_bg, _, _ = compute_binned_spectra(
            np.array(bg_temps_all), V_drop_L, dilution_factor=1.0
        )
        bg_kT[cond] = k_bg
    else:
        bg_kT[cond] = np.zeros(len(T_BINS))

records = []
summary  = []

for exp in experiments:
    meta    = parse_name(exp)
    chiller = meta["condition"]

    if meta["dilution"] == "D0":
        continue

    try:
        df_raw = load_and_calibrate(interim_dir, exp, chiller)
    except Exception as e:
        print(f"Error loading {exp}: {e}")
        continue

    T_freeze   = df_raw["T_cal"].values      # calibrated temperatures
    sigma_T    = float(df_raw["T_sigma"].mean())
    dil_factor = dilution_factor_map.get(meta["dilution"], 1)

    # Continuous frozen fraction + CI
    temps, ff, ff_lo, ff_hi = frozen_fraction_with_ci(T_freeze)
    K, K_lo, K_hi           = KT_uncertainty(ff, ff_lo, ff_hi, V_drop_L, dil_factor)

    # Binned spectra (L units, for KT_grid which reports L⁻¹)
    t_bins, N_bin, N_unfrz, k_T, K_T_binned, valid_mask = compute_binned_spectra(
        T_freeze, V_drop_L, dil_factor
    )

    # Background correction
    k_bg       = bg_kT.get(chiller, np.zeros(len(T_BINS)))
    k_T_corr, K_T_corr = background_correct_binned(k_T, k_bg * dil_factor)

    records.append({
        **meta,
        "temps":      temps,
        "ff":         ff,
        "ff_lo":      ff_lo,
        "ff_hi":      ff_hi,
        "K":          K,
        "K_lo":       K_lo,
        "K_hi":       K_hi,
        "t_bins":     t_bins,
        "N_bin":      N_bin,
        "valid_mask": valid_mask,     # True only where data exists (no plateau)
        "k_T":        k_T,
        "K_T_binned": K_T_binned,
        "k_T_corr":   k_T_corr,
        "K_T_corr":   K_T_corr,
        "sigma_T":    sigma_T,
        "n_wells":    len(T_freeze),
    })

    summary.append({
        **meta,
        "n_wells":      len(T_freeze),
        "sigma_T":      round(sigma_T, 3),
        "T10":          round(temp_at_ff(temps, ff, 0.10), 2),
        "T50":          round(temp_at_ff(temps, ff, 0.50), 2),
        "T90":          round(temp_at_ff(temps, ff, 0.90), 2),
        "K_T50":        float(np.interp(
                            -temp_at_ff(temps, ff, 0.50),
                            -temps[::-1], K[::-1]
                        )),
        "dilution_num": dilution_to_numeric(meta["dilution"]),
    })

summary_df = (
    pd.DataFrame(summary)
    .sort_values(["condition", "dilution_num", "plate", "run"])
    .reset_index(drop=True)
)
summary_df.to_csv(output_dir / "summary.csv", index=False)
print(f"Loaded {len(records)} experiments. Summary saved.")


# ─────────────────────────────────────────────────────────────────────
# 8. PLOTS
# ─────────────────────────────────────────────────────────────────────

conditions = sorted(set(r["condition"] for r in records))
nrows_grid = math.ceil(len(conditions) / 2)
ncols_grid = 2


# ── 8a. Frozen fraction grid ─────────────────────────────────────────

def make_ff_grid(records, conditions):
    fig, axes = plt.subplots(
        nrows_grid, ncols_grid, figsize=(12, 4.5 * nrows_grid),
        sharex=True, sharey=True
    )
    axes = np.atleast_1d(axes).ravel()
    legend_handles = {}

    for ax, cond in zip(axes, conditions):
        for r in records:
            if r["condition"] != cond:
                continue
            color  = color_map.get(r["dilution"], "gray")
            ls     = linestyle_map.get(r["plate"], "-")
            mk     = marker_map.get(r["run"], "o")
            label  = f"{r['dilution']}_{r['plate']}_{r['run']}"

            # ±σ_T calibration band (horizontal uncertainty on T axis)
            ax.fill_betweenx(
                r["ff"],
                r["temps"] - r["sigma_T"],
                r["temps"] + r["sigma_T"],
                color=color, alpha=0.08,
            )
            line, = ax.plot(
                r["temps"], r["ff"],
                color=color, ls=ls, marker=mk, ms=3, lw=1.4, alpha=0.9, label=label,
            )
            legend_handles.setdefault(label, line)

        ax.set_title(cond)
        ax.set_xlim(-35, 0)
        ax.set_ylim(0, 1.02)
        ax.grid(True, alpha=0.3)
        ax.set_xlabel("Temperature (°C)")
        ax.set_ylabel("Frozen fraction")

    for ax in axes[len(conditions):]:
        ax.axis("off")

    fig.legend(
        legend_handles.values(), legend_handles.keys(),
        loc="center right", fontsize=8, title="dilution_plate_run",
        bbox_to_anchor=(1.0, 0.5),
    )
    fig.suptitle("Frozen fraction f(T) — shading = ±σ_T calibration", y=1.01)
    plt.tight_layout(rect=[0, 0, 0.86, 1.0])
    return fig


# ── 8b. K(T) grid ────────────────────────────────────────────────────
# Shows: Agresti-Coull CI band + continuous K(T) + binned uncorrected
# + binned bg-corrected.  All clipped to valid range (no plateau).

def make_KT_grid(records, conditions):
    fig, axes = plt.subplots(
        nrows_grid, ncols_grid, figsize=(12, 4.5 * nrows_grid),
        sharex=True, sharey=True
    )
    axes = np.atleast_1d(axes).ravel()
    legend_handles = {}

    for ax, cond in zip(axes, conditions):
        for r in records:
            if r["condition"] != cond:
                continue
            color = color_map.get(r["dilution"], "gray")
            ls    = linestyle_map.get(r["plate"], "-")
            mk    = marker_map.get(r["run"], "o")
            label = f"{r['dilution']}_{r['plate']}_{r['run']}"
            vm    = r["valid_mask"]   # clip plateau

            # Agresti-Coull CI band (continuous)
            ax.fill_between(r["temps"], r["K_lo"], r["K_hi"],
                            color=color, alpha=0.10)

            # Continuous K(T)
            line, = ax.plot(
                r["temps"], r["K"],
                color=color, ls=ls, marker=mk, ms=3, lw=1.4, alpha=0.9, label=label,
            )
            legend_handles.setdefault(label, line)

            # Binned uncorrected — clipped to valid range
            ax.plot(r["t_bins"][vm], r["K_T_binned"][vm],
                    color=color, ls="-", lw=1.5, alpha=0.85)

            # Binned bg-corrected — clipped to valid range
            ax.plot(r["t_bins"][vm], r["K_T_corr"][vm],
                    color=color, ls=":", lw=1.5, alpha=0.85)

        ax.set_title(cond)
        ax.set_xlim(-35, 0)
        ax.set_yscale("log")
        ax.grid(True, alpha=0.3, which="both")
        ax.set_xlabel("Temperature (°C)")
        ax.set_ylabel("K(T)  [INP L$^{-1}$]")

    for ax in axes[len(conditions):]:
        ax.axis("off")

    fig.legend(
        legend_handles.values(), legend_handles.keys(),
        loc="center right", fontsize=8, title="dilution_plate_run",
        bbox_to_anchor=(1.0, 0.5),
    )
    fig.suptitle(
        "K(T) — shading = Agresti-Coull 95% CI\n"
        "solid = continuous, thick solid = binned uncorr., dotted = binned bg-corr.",
        y=1.01,
    )
    plt.tight_layout(rect=[0, 0, 0.86, 1.0])
    return fig


# ── 8c. T50 vs dilution ──────────────────────────────────────────────

def make_T50_vs_dilution(summary_df):
    fig, ax = plt.subplots(figsize=(7, 5))
    for cond, sub in summary_df.groupby("condition"):
        sub = sub.dropna(subset=["dilution_num", "T50"]).copy()
        g   = sub.groupby("dilution_num")["T50"]
        x   = np.array(sorted(g.groups.keys()))
        T50_mean = g.mean().reindex(x).values
        T50_min  = g.min().reindex(x).values
        T50_max  = g.max().reindex(x).values
        ax.errorbar(x, T50_mean,
                    yerr=[T50_mean - T50_min, T50_max - T50_mean],
                    fmt="-o", capsize=4, label=cond)
    ax.set_xscale("log")
    ax.invert_yaxis()
    ax.set_xlabel("Dilution factor")
    ax.set_ylabel("T50 (°C)")
    ax.grid(True, alpha=0.3, which="both")
    ax.legend(title="Condition")
    ax.set_title("T50 vs dilution (mean ± range of replicates)")
    plt.tight_layout()
    return fig


# ── 8d. Grouped binned K(T) [INP mL⁻¹] ─────────────────────────────
# One panel per chiller × dilution.
# Shows: replicate range band, Agresti-Coull CI band, pooled uncorrected,
# pooled bg-corrected. All clipped to valid range (no plateau).

def make_binned_grouped_plot(records, bg_kT):
    fig, axes = plt.subplots(1, len(CHILLERS),
                             figsize=(7 * len(CHILLERS), 6),
                             sharey=True)

    for ax, chiller in zip(axes, CHILLERS):
        for dil in DILUTIONS_ORDERED:
            group = [r for r in records
                     if r["condition"] == chiller and r["dilution"] == dil]
            if not group:
                continue

            color  = color_map.get(dil, "gray")
            dil_f  = dilution_factor_map.get(dil, 1)

            # Individual replicates (thin, transparent)
            rep_KT = []
            for r in group:
                _, N_bin_i, _, _, K_ind, vm_i = compute_binned_spectra(
                    r["temps"], V_drop_mL, dilution_factor=dil_f
                )
                ax.plot(T_BINS[vm_i], K_ind[vm_i],
                        color=color, lw=0.8, alpha=0.25,
                        ls=linestyle_map.get(r["plate"], "-"))
                rep_KT.append(K_ind)

            rep_KT = np.array(rep_KT)

            # Pooled
            T_all   = np.concatenate([r["temps"] for r in group])
            N_total = len(T_all)
            _, N_bin_pool, _, k_pool, K_pool, vm = compute_binned_spectra(
                T_all, V_drop_mL, dilution_factor=dil_f
            )

            # Agresti-Coull CI
            N_frozen_cum = np.cumsum(N_bin_pool)
            n_tilde = N_frozen_cum + CI_Z ** 2 / 2
            N_tilde = N_total + CI_Z ** 2
            p_tilde = n_tilde / N_tilde
            margin  = CI_Z * np.sqrt(p_tilde * (1 - p_tilde) / N_tilde)
            ff_lo   = np.clip(p_tilde - margin, 1e-9, 1 - 1e-9)
            ff_hi   = np.clip(p_tilde + margin, 1e-9, 1 - 1e-9)
            K_lo    = -np.log(1 - ff_lo) / V_drop_mL * dil_f
            K_hi    = -np.log(1 - ff_hi) / V_drop_mL * dil_f

            # Background correction
            k_bg_scaled    = bg_kT.get(chiller, np.zeros(len(T_BINS))) * dil_f
            k_corr, K_corr = background_correct_binned(k_pool, k_bg_scaled)
            vm_corr        = vm & (K_corr > 0)

            pos = np.where((vm) & (k_corr > 0))[0]
            vm_corr = np.zeros_like(vm, dtype=bool)
            if len(pos) > 2:
                vm_corr[pos[0] + 1:pos[-1]] = True

            # Replicate envelope
            if rep_KT.shape[0] > 1:
                ax.fill_between(T_BINS[vm],
                                np.min(rep_KT, axis=0)[vm],
                                np.max(rep_KT, axis=0)[vm],
                                color=color, alpha=0.10)

            # CI band
            ax.fill_between(T_BINS[vm], K_lo[vm], K_hi[vm],
                            color=color, alpha=0.22)

            # Pooled uncorrected
            ax.plot(T_BINS[vm], K_pool[vm],
                    color=color, lw=2.0, ls="-",
                    label=f"{dil} (n={N_total})")

            # Pooled bg-corrected
            ax.plot(T_BINS[vm_corr], K_corr[vm_corr],
                    color=color, lw=2.0, ls="--")

        ax.set_title(chiller, fontsize=12)
        ax.set_yscale("log")
        ax.set_xlim(-35, 0)
        ax.set_ylim(1e-1, 1e5)
        ax.grid(True, alpha=0.3, which="both")
        ax.set_xlabel("Temperature (°C)")
        ax.set_ylabel("K(T)  [INP mL$^{-1}$]")
        ax.legend(title="Dilution  (solid=uncorr., dashed=bg-corr.)",
                  fontsize=8, loc="lower left")

    fig.suptitle(
        "Binned K(T)  [ΔT = 0.5 °C]  —  "
        "bands = Agresti-Coull CI + replicate range\n"
        "first & last active bins trimmed (numerical artefact)",
        fontsize=10,
    )
    plt.tight_layout()
    return fig


# ─────────────────────────────────────────────────────────────────────
# 9. CSV EXPORT (organizer format)
# ─────────────────────────────────────────────────────────────────────

def export_organizer_csv(records, bg_kT, output_dir):
    """
    One row per valid bin per chiller × dilution combination.
    Bins after the last freezing event (plateau) are excluded.
    Units: K(T) in INP mL⁻¹, temperature in K.
    """
    all_rows = []

    for chiller in CHILLERS:
        for dil in DILUTIONS_ORDERED:
            group = [r for r in records
                     if r["condition"] == chiller and r["dilution"] == dil]
            if not group:
                continue

            dil_f   = dilution_factor_map.get(dil, 1)
            T_all   = np.concatenate([r["temps"] for r in group])
            N_total = len(T_all)

            # Pooled binned spectra (mL units)
            _, N_bin, _, k_pool, K_pool, vm = compute_binned_spectra(
                T_all, V_drop_mL, dilution_factor=dil_f
            )

            # Agresti-Coull CI on pooled
            N_frozen_cum = np.cumsum(N_bin)
            n_tilde = N_frozen_cum + CI_Z ** 2 / 2
            N_tilde = N_total + CI_Z ** 2
            p_tilde = n_tilde / N_tilde
            margin  = CI_Z * np.sqrt(p_tilde * (1 - p_tilde) / N_tilde)
            ff_lo   = np.clip(p_tilde - margin, 1e-9, 1 - 1e-9)
            ff_hi   = np.clip(p_tilde + margin, 1e-9, 1 - 1e-9)
            K_lo    = -np.log(1 - ff_lo) / V_drop_mL * dil_f
            K_hi    = -np.log(1 - ff_hi) / V_drop_mL * dil_f

            # Background correction
            k_bg_scaled    = bg_kT.get(chiller, np.zeros(len(T_BINS))) * dil_f
            k_corr, K_corr = background_correct_binned(k_pool, k_bg_scaled)
            K_corr_lo = np.maximum(K_lo - np.cumsum(k_bg_scaled * BIN_DT), 0)
            K_corr_hi = np.maximum(K_hi - np.cumsum(k_bg_scaled * BIN_DT), 0)

            # Only export valid bins (vm = first to last event, no plateau)
            for i in np.where(vm)[0]:
                all_rows.append({
                    "instrument":      chiller,
                    "dilution":        dil,
                    "T_K":             round(T_BINS_K[i], 2),
                    "T_uncertainty_K": round(sigma_T_at_bin(T_BINS[i], chiller), 4),
                    "K_mL":            float(K_pool[i]),
                    "K_mL_lo":         float(K_lo[i]),
                    "K_mL_hi":         float(K_hi[i]),
                    "K_mL_bgcorr":     float(K_corr[i]),
                    "K_mL_bgcorr_lo":  float(K_corr_lo[i]),
                    "K_mL_bgcorr_hi":  float(K_corr_hi[i]),
                    "n_wells":         N_total,
                })

    df_out = pd.DataFrame(all_rows)
    path   = output_dir / "FrESH_KIT_INP_spectra.csv"
    df_out.to_csv(path, index=False, float_format="%.6e")
    print(f"Exported {len(df_out)} rows → {path}")
    return df_out

color_map = {
    "D1":   "#0072B2",
    "D10":  "#D55E00",
    "D100": "#009E73",
}

chiller_style = {
    "RE1050": {"ls": "-",  "lw": 2.3, "alpha": 0.95},
    "RP1845": {"ls": "--", "lw": 2.3, "alpha": 0.95},
}

def add_cs_curves(ax, cs_dict):
    for dil, df_cs in cs_dict.items():
        if df_cs is None or df_cs.empty:
            continue

        color = color_map.get(dil, "gray")
        T    = df_cs["T_C"].values
        K    = df_cs["K_mL"].values
        K_lo = df_cs["K_mL_lo"].values
        K_hi = df_cs["K_mL_hi"].values

        ax.fill_between(
            T, K_lo, K_hi,
            color=color, alpha=0.10, linewidth=0
        )

        ax.plot(
            T, K,
            color=color, lw=2.0, linestyle="-",
            marker="o", ms=3, markevery=2,
            mec="white", mew=0.4,
            label=f"{dil} CS"
        )

def make_binned_all_chillers_one_panel(records, bg_kT):
    fig, ax = plt.subplots(figsize=(8.5, 6.5))

    for chiller in CHILLERS:
        for dil in DILUTIONS_ORDERED:
            group = [r for r in records
                     if r["condition"] == chiller and r["dilution"] == dil]
            if not group:
                continue

            color = color_map.get(dil, "gray")
            dil_f = dilution_factor_map.get(dil, 1)
            style = chiller_style.get(chiller, {"ls": "-", "lw": 2.0, "alpha": 0.95})

            T_all   = np.concatenate([r["temps"] for r in group])
            N_total = len(T_all)

            _, N_bin_pool, _, k_pool, K_pool, vm = compute_binned_spectra(
                T_all, V_drop_mL, dilution_factor=dil_f
            )

            N_frozen_cum = np.cumsum(N_bin_pool)
            n_tilde = N_frozen_cum + CI_Z ** 2 / 2
            N_tilde = N_total + CI_Z ** 2
            p_tilde = n_tilde / N_tilde
            margin  = CI_Z * np.sqrt(p_tilde * (1 - p_tilde) / N_tilde)
            ff_lo   = np.clip(p_tilde - margin, 1e-9, 1 - 1e-9)
            ff_hi   = np.clip(p_tilde + margin, 1e-9, 1 - 1e-9)
            K_lo    = -np.log(1 - ff_lo) / V_drop_mL * dil_f
            K_hi    = -np.log(1 - ff_hi) / V_drop_mL * dil_f

            k_bg_scaled    = bg_kT.get(chiller, np.zeros(len(T_BINS))) * dil_f
            k_corr, K_corr = background_correct_binned(k_pool, k_bg_scaled)

            pos = np.where((vm) & (k_corr > 0))[0]
            vm_corr = np.zeros_like(vm, dtype=bool)
            if len(pos) > 2:
                vm_corr[pos[0] + 1:pos[-1]] = True

            ax.fill_between(
                T_BINS[vm], K_lo[vm], K_hi[vm],
                color=color, alpha=0.08, linewidth=0
            )

            ax.plot(
                T_BINS[vm], K_pool[vm],
                color=color, lw=1.0, alpha=0.18, linestyle=style["ls"]
            )

            ax.plot(
                T_BINS[vm_corr], K_corr[vm_corr],
                color=color,
                linestyle=style["ls"],
                lw=style["lw"],
                alpha=style["alpha"],
                label=f"{dil} {chiller}"
            )

    cs_curves = {"D1": cs_D1, "D10": cs_D10, "D100": cs_D100}
    add_cs_curves(ax, cs_curves)

    ax.set_yscale("log")
    ax.set_xlim(-35, 0)
    ax.set_ylim(1e-1, 1e6)

    ax.set_xlabel("Temperature (°C)")
    ax.set_ylabel("K(T) [INP mL$^{-1}$]")

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(True, which="major", alpha=0.22)
    ax.grid(True, which="minor", alpha=0.08)

    ax.set_title("KIT suspension: K(T) by dilution and instrument", pad=10)

    leg = ax.legend(
        fontsize=8,
        ncol=2,
        frameon=False,
        loc="lower left"
    )

    plt.tight_layout()
    return fig


# ─────────────────────────────────────────────────────────────────────
# 10. RUN ALL PLOTS + SAVE
# ─────────────────────────────────────────────────────────────────────
def load_cs_spectra_to_KT(cs_csv_path, dilution_factor, V_drop_mL_cs=1e-3):
    """
    Lee spectra.csv del cold stage y calcula K(T) [INP mL^-1] a partir de FF.

    Parameters
    ----------
    cs_csv_path : Path or str
        Ruta a spectra.csv del CS.
    dilution_factor : float
        Factor de dilución (1, 10, 100, ...).
    V_drop_mL_cs : float
        Volumen de gota del CS en mL (por defecto 1 µL = 1e-3 mL).

    Returns
    -------
    df : DataFrame con columnas:
        T_C, ff, ff_lo, ff_hi, K_mL, K_mL_lo, K_mL_hi
    """
    df = pd.read_csv(cs_csv_path)

    T_C   = df["temp_calibrated(degrees_Celsius)"].values
    ff    = df[" ff"].values
    ff_lo = df[" ff_lower_conf_lvl"].values
    ff_hi = df[" ff_upper_conf_lvl"].values

    def KT_from_ff_array(f):
        f_clipped = np.clip(f, 1e-9, 1 - 1e-9)
        return -np.log(1 - f_clipped) / V_drop_mL_cs * dilution_factor

    K     = KT_from_ff_array(ff)
    K_lo  = KT_from_ff_array(ff_lo)
    K_hi  = KT_from_ff_array(ff_hi)

    out = pd.DataFrame({
        "T_C":   T_C,
        "ff":    ff,
        "ff_lo": ff_lo,
        "ff_hi": ff_hi,
        "K_mL":     K,
        "K_mL_lo":  K_lo,
        "K_mL_hi":  K_hi,
    }).sort_values("T_C")

    return out

cs_base = Path("/home/perezfo/PycharmProjects/FrESH/data/external/KIT_Intercomparison")

cs_D1  = load_cs_spectra_to_KT(cs_base / "sample_original" / "spectra.csv", dilution_factor=1)
cs_D10 = load_cs_spectra_to_KT(cs_base / "1_10" / "spectra.csv",           dilution_factor=10)
cs_D100= load_cs_spectra_to_KT(cs_base / "1_100" / "spectra.csv",          dilution_factor=100)


figs = {
    "ff_grid.png":          make_ff_grid(records, conditions),
    "KT_grid.png":          make_KT_grid(records, conditions),
    "T50_vs_dilution.png":  make_T50_vs_dilution(summary_df),
    "KT_grouped_binned.png": make_binned_grouped_plot(records, bg_kT),
    "KT_all_chillers_one_panel.png": make_binned_all_chillers_one_panel(records, bg_kT),
}


for fname, fig in figs.items():
    path = output_dir / fname
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {path}")

df_export = export_organizer_csv(records, bg_kT, output_dir)

print("\nAll done.")