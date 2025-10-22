# src/analysis/hub_batch.py
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from typing import Optional, Dict, Any
from src.utils.hub_backward_lib  import hub_backward_fit, vali_from_fice  # importa tu módulo no interactivo

def _load_fice_from_report(report_csv: str, round_dec: int = 4):
    # Lectura robusta y detección de columnas
    try:
        df = pd.read_csv(report_csv, sep=None, engine="python")
    except Exception:
        df = pd.read_csv(report_csv, delim_whitespace=True, engine="python")
    cols = {c.lower().strip(): c for c in df.columns}
    # Detecta temperatura
    tcol = None
    for k in ["temp","temperature","t","temps"]:
        if k in cols: tcol = cols[k]; break
    # Detecta fracción congelada
    fcol = None
    for k in ["ff","fice","fraction_frozen","frozen_fraction","fractionofice","fraction_of_ice"]:
        if k in cols: fcol = cols[k]; break
    # Fallback a dos primeras numéricas
    if tcol is None or fcol is None:
        num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        if len(num_cols) >= 2:
            tcol, fcol = num_cols[0], num_cols[1]
        else:
            raise ValueError(f"No se encuentran columnas numéricas adecuadas en {report_csv}")
    # Limpieza y orden
    T = pd.to_numeric(df[tcol], errors="coerce").astype(float)
    f = pd.to_numeric(df[fcol], errors="coerce").astype(float)
    m = np.isfinite(T.values) & np.isfinite(f.values)
    T, f = T[m].values, f[m].values
    order = np.argsort(T)
    T, f = T[order], f[order]
    # Agrupa por T redondeada y toma el máximo de f por estabilidad
    dfg = pd.DataFrame({"T": np.round(T, round_dec), "f": f}).groupby("T", as_index=False)["f"].max()
    # Clipa y fuerza monotonía no creciente vs T ascendente
    fv = np.clip(dfg["f"].to_numpy(), 0.0, 1.0)
    fmono = np.maximum.accumulate(fv[::-1])[::-1]
    return dfg["T"].to_numpy(), fmono

def _load_spectra_csv(spectra_csv: str):
    if not os.path.isfile(spectra_csv):
        return None
    df = pd.read_csv(spectra_csv)
    cols = {c.lower().strip(): c for c in df.columns}
    # Temperatura
    T_col = None
    for k in ["t","temp","temperature"]:
        if k in cols: T_col = cols[k]; break
    if T_col is None:
        T_col = df.columns[0]
    # Nm (acumulativo)
    Nm_col = None
    for k in ["nm","n_m","cumulative","cum"]:
        if k in cols:
            Nm_col = cols[k]; break
    # nm (diferencial)
    nm_col = None
    for k in ["nm_diff","nmdiff","nm_differential","diff","differential","n_m"]:
        if k in cols and cols[k] != Nm_col:
            nm_col = cols[k]; break
    T = df[T_col].to_numpy(dtype=float)
    Nm = df[Nm_col].to_numpy(dtype=float) if Nm_col in df else None
    nm = df[nm_col].to_numpy(dtype=float) if nm_col in df else None
    return {"T": T, "Nm": Nm, "nm": nm}

def run_hub_for_experiment(
    exp_dir: str,
    reports_dir: str,
    nsubpop: int = 2,
    disttype: int = 1,  # 1=Gaussian
    npoints: int = 300,
    window_length: int = 7,
    polyorder: int = 2,
    save_txt: bool = True,
    save_pdf: bool = True,
    plot_cumulative: bool = True
) -> Dict[str, Any]:
    os.makedirs(reports_dir, exist_ok=True)
    report_csv = os.path.join(exp_dir.replace('raw','processed'), "report.csv")
    spectra_csv = os.path.join(exp_dir.replace('raw','processed'), "spectra.csv")
    if not os.path.isfile(report_csv):
        raise FileNotFoundError(f"No existe report.csv en {exp_dir}")
    # Construir fice(T)
    T, f = _load_fice_from_report(report_csv)
    # Ejecutar HUB-backward (target=fice)
    out = hub_backward_fit(T, f, target="fice", nsubpop=nsubpop, disttype=disttype,
                           npoints=npoints, window_length=window_length, polyorder=polyorder,
                           save_prefix=None)
    # Cargar espectros externos (opcional)
    spec = _load_spectra_csv(spectra_csv)
    # Construir Nm de HUB desde fice optimizado (escala relativa)
    Nm_hub = vali_from_fice(out["yhat"], X=1.0)
    # Rutas de salida
    exp_name = os.path.basename(os.path.normpath(exp_dir))
    base = os.path.join(reports_dir, f"{exp_name}_HUB")
    # Guardar TXT
    if save_txt:
        np.savetxt(base + "_Target_optimized.txt",
                   np.column_stack([out["Tfit"], out["yhat"]]),
                   fmt="%.6f %.10f", header="Temperature, fice", comments="")
        np.savetxt(base + "_nm_differential_freezing_spectrum.txt",
                   np.column_stack([out["Tnm"], out["nm"]]),
                   fmt="%.6f %.10f", header="Temperature, nm", comments="")
        np.savetxt(base + "_Nm_from_HUB.txt",
                   np.column_stack([out["Tfit"], Nm_hub]),
                   fmt="%.6f %.10f", header="Temperature, Nm(HUB from fice)", comments="")
    # Graficar subplots comparativos
    if save_pdf:
        if plot_cumulative and (spec is not None) and (spec["Nm"] is not None):
            fig, axes = plt.subplots(1, 3, figsize=(16,5), constrained_layout=True)
        else:
            fig, axes = plt.subplots(1, 2, figsize=(12,5), constrained_layout=True)
        ax1, ax2 = axes[0], axes[1]
        # fice
        ax1.plot(T, f, "o", ms=5, mfc="none", mec="k", label="fice input")
        ax1.plot(out["Tfit"], out["yfit_smooth"], "-", c="magenta", lw=2, label="spline")
        ax1.plot(out["Tfit"], out["yhat"], "-", c="red", lw=2.5, label="HUB fit")
        ax1.set_xlabel("T (°C)")
        ax1.set_ylabel("Fraction of ice")
        ax1.grid(True, which="both", alpha=0.3)
        ax1.legend(frameon=False)
        # nm
        ax2.plot(out["Tnm"], out["nm"], "-", c="red", lw=2.5, label="n_m (HUB)")
        if (spec is not None) and (spec["nm"] is not None):
            ax2.plot(spec["T"], spec["nm"], "o", ms=5, mfc="none", mec="C0", label="n_m (spectra.csv)")
        ax2.set_yscale("log")
        ax2.set_yscale("linear")
        ax2.set_ylim(bottom=0)
        ax2.set_ylim(0.0001, 1)
        ax2.set_xlim(-30, 0)
        ax2.set_xlabel("T (°C)")
        ax2.set_ylabel("n_m")
        ax2.grid(True, which="both", alpha=0.3)
        ax2.legend(frameon=False)
        # Nm (opcional)
        if plot_cumulative and (spec is not None) and (spec["Nm"] is not None):
            ax3 = axes[2]
            ax3.plot(out["Tfit"], Nm_hub, "-", c="C1", lw=2.5, label="N_m (HUB from fice)")
            ax3.plot(spec["T"], spec["Nm"], "o", ms=5, mfc="none", mec="C0", label="N_m (spectra.csv)")
            ax3.set_yscale("log")
            ax3.set_xlabel("T (°C)")
            ax3.set_ylabel("N_m")
            ax3.grid(True, which="both", alpha=0.3)
            ax3.legend(frameon=False)
        fig.suptitle(f"{exp_name} | MSE: {out['mse']:.4g}")
        fig.savefig(base + "_report.jpg", dpi=200)
        plt.close(fig)
    return {"experiment": exp_name, "mse": out["mse"], "best_params": out["best_params"], "out_base": base}
