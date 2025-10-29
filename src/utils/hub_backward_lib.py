# hub_backward_lib.py
import numpy as np
import pandas as pd
from scipy.signal import savgol_filter
from scipy.interpolate import interp1d
from scipy.optimize import dual_annealing
import matplotlib.pyplot as plt
import os

# -----------------------
# Distribuciones base
# -----------------------

def _truncate_negative_T(x, pdf):
    x = np.asarray(x, float)
    pdf = np.asarray(pdf, float)
    mask = (x <= 0.0)
    out = np.zeros_like(pdf)
    if np.any(mask):
        area = np.trapz(pdf[mask], x[mask])
        if np.isfinite(area) and area > 0:
            out[mask] = pdf[mask] / area
    out[~np.isfinite(out)] = 0.0
    return out

def normalized_PDF(x, mode, scale, disttype=1, enforce_negative_T=True):
    # disttype: 1=Gaussian, 2=Log-normal (x>mode), 3=Gumbel left-tail
    x = np.asarray(x, dtype=float)
    if disttype == 1:
        pdf = (1.0 / (scale * np.sqrt(2*np.pi))) * np.exp(-0.5 * ((x - mode) / scale)**2)
    elif disttype == 2:
        z = (x - mode)
        pdf = np.zeros_like(x, dtype=float)
        mask = z > 0
        pdf[mask] = (1.0 / (z[mask] * scale * np.sqrt(2*np.pi))) * np.exp(-0.5 * (np.log(z[mask]) / scale)**2)
    elif disttype == 3:
        pdf = (1.0 / scale) * np.exp((x - mode)/scale - np.exp((x - mode)/scale))
    else:
        raise ValueError("disttype must be 1, 2 or 3")
    pdf[~np.isfinite(pdf)] = 0.0
    if enforce_negative_T:
        pdf = _truncate_negative_T(x, pdf)
    return pdf


# -----------------------
# Utilidades de preproceso
# -----------------------
def _ensure_monotone_fice(T, f):
    # Fuerza fice no creciente con T ascendente (f grande a T baja)
    f = np.asarray(f, dtype=float)
    return np.maximum.accumulate(f[::-1])[::-1]

def preprocess_target(temp, y, target="fice", npoints=100, window_length=3, polyorder=1, enforce_monotone=True):
    T = np.asarray(temp, dtype=float)
    Y = np.asarray(y, dtype=float)
    m = np.isfinite(T) & np.isfinite(Y)
    T, Y = T[m], Y[m]
    order = np.argsort(T)
    T, Y = T[order], Y[order]
    if target == "fice" and enforce_monotone:
        Y = np.clip(Y, 0.0, 1.0)
        Y = _ensure_monotone_fice(T, Y)
    f = interp1d(T, Y, kind="linear", fill_value="extrapolate", bounds_error=False)
    Tfit = np.linspace(T.min(), T.max(), num=npoints)
    Yfit = f(Tfit)
    if window_length % 2 == 0:
        window_length += 1
    window_length = min(window_length, max(3, npoints - (1 - npoints % 2)))
    Yfit_smooth = savgol_filter(Yfit, window_length, polyorder)
    return Tfit, Yfit_smooth, (T, Y)

def vali_from_fice(fice, X=1.0):
    # Nm = -(1/X) ln(1 - fice); si X=1.0, escala relativa coherente
    f = np.clip(np.asarray(fice, dtype=float), 0.0, 0.999999)
    return -(1.0 / X) * np.log(1.0 - f)

# -----------------------
# Construcción forward (para evaluar objetivo)
# -----------------------
def _mixture_prob(x, param, nsubpop, disttype):
    if nsubpop == 1:
        p = normalized_PDF(x, param[0], param[1], disttype)
    elif nsubpop == 2:
        w2 = param[4]
        p1 = normalized_PDF(x, param[0], param[1], disttype)
        p2 = normalized_PDF(x, param[2], param[3], disttype)
        p = (1 - w2) * p1 + w2 * p2
    elif nsubpop == 3:
        w2, w3 = param[4], param[7]
        p1 = normalized_PDF(x, param[0], param[1], disttype)
        p2 = normalized_PDF(x, param[2], param[3], disttype)
        p3 = normalized_PDF(x, param[5], param[6], disttype)
        p = (1 - w2 - w3) * p1 + w2 * p2 + w3 * p3
    else:
        raise ValueError("nsubpop must be 1, 2, or 3")
    p[np.isnan(p)] = 0.0
    return p

def _forward_target(Tfit, param, nsubpop, disttype, target, scale_factor):
    # Integra mezcla para fice o Nm (singular)
    Prob = _mixture_prob(Tfit, param, nsubpop, disttype)
    dT = Tfit[1] - Tfit[0]
    integral = np.cumsum(Prob) * dT
    if target == "Nm":
        # g = -ln(1 - beta*(1 - integral)), escala con factor
        beta = param[-1]  # último parámetro reservado para beta en Nm
        g = -np.log(np.clip(1.0 - beta * (1.0 - integral), 1e-12, 1.0))
        return g * scale_factor
    else:
        # fice = beta*(1 - integral / max(integral)); beta=1 para fice
        f = 1.0 * (1.0 - integral / max(integral) if max(integral) > 0 else integral)
        return np.clip(f, 0.0, 1.0)

# -----------------------
# Función de ajuste principal
# -----------------------
def hub_backward_fit(
    temp, y, target="fice",
    nsubpop=1,
    disttype=1,  # 1=Gaussian
    npoints=100,
    window_length=3,
    polyorder=1,
    bounds=None,
    initial_guess=None,
    random_seed=None,
    save_prefix=None,
    return_intermediate=True
):
    """
    Ajusta HUB-backward para fice(T) o Nm(T) y devuelve parámetros, MSE y nm(T).
    """
    assert target in ("fice", "Nm")
    # Preproceso
    Tfit, Yfit_smooth, (Traw, Yraw) = preprocess_target(temp, y, target=target, npoints=npoints,
                                                        window_length=window_length, polyorder=polyorder,
                                                        enforce_monotone=(target=="fice"))
    # Bounds por defecto
    if bounds is None:
        if nsubpop == 1:
            bnds = [[-30, 0], [0.1, 10], [1e-3, 1]] if target == "Nm" else [[-30, 0], [0.1, 10],]
        elif nsubpop == 2:
            bnds = [[-30, 0], [0.1, 10], [-30, 0], [0.1, 10], [1e-10, 1], [1e-3, 1]] if target == "Nm" \
                   else [[-30, 0], [0.1, 10], [-30, 0], [0.1, 10], [1e-10, 1]]
        else:
            bnds = [[-30, 0], [0.1, 10], [-30, 0], [0.1, 10], [1e-10, 1], [-30, 0], [0.1, 10], [1e-10, 1e-2], [1e-3, 1]] if target == "Nm" \
                   else [[-30, 0], [0.1, 10], [-30, 0], [0.1, 10], [1e-10, 1], [-30, 0], [0.1, 10], [1e-10, 1e-2]]

    else:
        bnds = bounds

    bnds = np.array(bnds, dtype=float)
    # Escala para Nm (usa amplitud del objetivo suave)
    scale_factor = max(Yfit_smooth) if target == "Nm" else 1.0

    # Objetivo
    def objective(param):
        yhat = _forward_target(Tfit, param, nsubpop, disttype, target=("Nm" if target=="Nm" else "fice"),
                               scale_factor=scale_factor)
        if target == "Nm":
            # MSE en log10 para Nm como en el script original
            eps = 1e-16
            yy = np.log10(np.clip(Yfit_smooth, eps, None))
            yh = np.log10(np.clip(yhat, eps, None))
            valid = np.isfinite(yy) & np.isfinite(yh) & (yhat > np.min(Yfit_smooth))
            if not np.any(valid):
                return 1e2
            return np.mean((yy[valid] - yh[valid])**2)
        else:
            return np.mean((Yfit_smooth - yhat)**2)

    # Semilla
    if random_seed is None:
        random_seed = np.random.randint(0, 2**32-1, dtype=np.uint64)

    # Inicial
    x0 = initial_guess if initial_guess is not None else None

    # Ajuste
    res = dual_annealing(objective, bounds=bnds, x0=x0, seed=int(random_seed), maxfun=200000)
    best = res.x
    mse = float(res.fun)

    # Reconstrucción ajustada en el eje del objetivo
    yhat = _forward_target(Tfit, best, nsubpop, disttype, target=("Nm" if target=="Nm" else "fice"),
                           scale_factor=scale_factor)

    # Construcción de nm(T) con malla extendida
    Tnm = np.linspace(Traw.min()-2.0, Traw.max()+2.0, num=npoints*2)
    # Mezcla subyacente
    nm = _mixture_prob(Tnm, best, nsubpop, disttype)
    nm[nm < 0] = 0.0

    # Guardados opcionales
    outputs = {
        "best_params": best,
        "mse": mse,
        "Tfit": Tfit,
        "yfit_smooth": Yfit_smooth,
        "yhat": yhat,
        "Tnm": Tnm,
        "nm": nm,
        "target": target,
        "nsubpop": nsubpop,
        "disttype": disttype,
        "random_seed": int(random_seed),
    }

    if save_prefix is not None:
        os.makedirs(os.path.dirname(save_prefix) or ".", exist_ok=True)
        # TXT compatibles
        np.savetxt(save_prefix + "_Target_optimized.txt", np.column_stack([Tfit, yhat]),
                   fmt="%.6f %.10f", header="Temperature, Nm or fice", comments="")
        np.savetxt(save_prefix + "_nm_differential_freezing_spectrum.txt",
                   np.column_stack([Tnm, nm]),
                   fmt="%.6f %.10f", header="Temperature, nm", comments="")
        # Plots básicos
        fig, ax = plt.subplots()
        ax.plot(Traw, Yraw, "o", ms=5, mfc="none", mec="k", label="input")
        ax.plot(Tfit, Yfit_smooth, "-", c="magenta", lw=2, label="spline")
        ax.plot(Tfit, yhat, "-", c="red", lw=3, label="optimized")
        ax.set_xlabel("T (°C)")
        ax.set_ylabel("N$_m$" if target=="Nm" else "Fraction of ice")
        if target == "Nm":
            ax.set_yscale("log")
        ax.legend()
        fig.tight_layout()
        fig.savefig(save_prefix + "_Figure_target_optimized.pdf", dpi=200)
        plt.close(fig)

        fig2, ax2 = plt.subplots()
        ax2.plot(Tnm, nm, "-", c="red", lw=3)
        ax2.set_yscale("log")
        ax2.set_xlabel("T (°C)")
        ax2.set_ylabel("n$_m$")
        fig2.tight_layout()
        fig2.savefig(save_prefix + "_Figure_nm.pdf", dpi=200)
        plt.close(fig2)

    return outputs if return_intermediate else {"best_params": best, "mse": mse, "Tnm": Tnm, "nm": nm}

# -----------------------
# Utilidad: construir fice desde temperaturas de gotas
# -----------------------
def build_fice_from_droplet_temps(drop_temps):
    t = np.sort(np.asarray(drop_temps, dtype=float))
    n = t.size
    f = np.arange(1, n+1, dtype=float) / n
    return t, f
