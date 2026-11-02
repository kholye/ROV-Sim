"""Подводный свет: модель формирования изображения (эталон для шейдера Godot).

Источники и статусы: docs/physics-sources.md, разд. 17-20. Числа: godot/physics/light_params.json.

Модель одного пикселя (однократное рассеяние, Jaffe 1990; McGlamery 1980; разделение прямого сигнала
и обратного рассеяния как у Akkaynak & Treibitz 2018). Для каждого канала c = R, G, B:

  L_c = ρ_c/π · E_c(P) · exp(−c_c·D)                         прямой сигнал от поверхности на дальности D
      + ∫₀ᴰ b_c · β̃(ψ) · I_c(θ)/r² · exp(−c_c·(r + t)) dt    обратное рассеяние света лампы вдоль луча
      + L∞_c · (1 − exp(−c_c·D))                              рассеяние рассеянного света сверху

  E_c(P) = I_c(θ_P)·max(0, cos i)/r_P² · exp(−c_c·r_P) + E_amb,c(P)
  I_c(θ) = I0 · w_c · cos θ  при θ < 90°  (ламбертов излучатель: полуширина 120°, Φ = π·I0)
  c_c = a_c + b_c,  b_c = b_w,c + b_p,c

β̃ — фазовая функция Фурнье-Форанд (Mobley 2002), n = 1,10, μ = 3,5835: доля рассеяния назад 0,0183
(как у усреднённой функции Петцольда). Прямое рассеяние вперёд (размытие) не моделируется.

Единицы: I0 в канделах (лм/π), E в люксах, L в кд/м². Камера: значение = экспозиция·L, обрезка 1, кривая sRGB.
Вектора — любые трёхмерные в одной системе; «вверх» передаётся явно (в Godot это +Y, в NED это −z).
"""
import json
from pathlib import Path

import numpy as np

PARAMS_PATH = Path(__file__).resolve().parents[2] / "godot" / "physics" / "light_params.json"
POPE = Path(__file__).resolve().parent / "data" / "pope97.txt"


def load(path=PARAMS_PATH, **overrides):
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    p = {k: v["value"] for k, v in raw.items() if not k.startswith("_")}
    for k, v in overrides.items():
        if k not in p:
            raise KeyError(k)
        p[k] = v
    return p


# ---------------- спектральная часть (только для расчёта коэффициентов каналов) ----------------

def pope_fry():
    """Длины волн (нм) и поглощение чистой воды (1/м), Pope & Fry 1997."""
    d = np.loadtxt(POPE, comments="#", encoding="utf-8")
    return d[:, 0], d[:, 1] * 100.0


def planck(lam_nm, T):
    lam = lam_nm * 1e-9
    return 1.0 / (lam ** 5 * (np.exp(1.4388e-2 / (lam * T)) - 1.0))


def band_weights(lam, centers, sigmas, T):
    """Вес длины волны в каждом канале: гауссова чувствительность камеры × спектр источника (Планк при T)."""
    s = planck(lam, T)
    return [np.exp(-0.5 * ((lam - c0) / s0) ** 2) * s for c0, s0 in zip(centers, sigmas)]


def effective_coeff(lam, k_lam, weights, path):
    """Эффективный коэффициент канала: −ln(Σ w·exp(−k·L)/Σ w)/L при длине пути L."""
    return [float(-np.log(np.sum(w * np.exp(-k_lam * path)) / np.sum(w)) / path) for w in weights]


# ---------------- фазовая функция ----------------

def phase_ff(cos_psi, n=1.10, mu=3.5835):
    """Фурнье-Форанд (Mobley et al. 2002, ф. 4), нормирована: ∫ β̃ dΩ = 1, 1/ср."""
    cos_psi = np.clip(cos_psi, -1.0, 1.0)
    nu = (3.0 - mu) / 2.0
    k = 4.0 / (3.0 * (n - 1.0) ** 2)
    s2 = np.maximum((1.0 - cos_psi) / 2.0, 1e-8)        # sin²(ψ/2)
    d = k * s2
    d = np.where(np.abs(1.0 - d) < 1e-4, 1.0 - 1e-4, d)  # устранимая особенность при δ = 1
    dn = d ** nu
    d180 = k
    d180n = d180 ** nu
    f = (nu * (1 - d) - (1 - dn) + (d * (1 - dn) - nu * (1 - d)) / s2) / (4 * np.pi * (1 - d) ** 2 * dn)
    return f + (1 - d180n) / (16 * np.pi * (d180 - 1) * d180n) * (3 * cos_psi ** 2 - 1)


# ---------------- вода и лампа ----------------

class Water:
    """Оптика воды в трёх каналах."""

    def __init__(self, p, b_p550=None, a_extra=None):
        self.a = np.array(p["water_a_rgb"], float) + np.array(a_extra if a_extra is not None else p["pool_a_extra_rgb"])
        bp = p["pool_bp550"] if b_p550 is None else b_p550
        self.b = np.array(p["water_bw_rgb"], float) + bp * np.array(p["particle_b_shape_rgb"], float)
        self.c = self.a + self.b
        self.n_ff, self.mu_ff = p["phase_ff_n"], p["phase_ff_mu"]
        self.bb_frac = p["phase_ff_bb"]
        self.mu_d = p["mean_cosine_down"]

    def beta(self, cos_psi):
        """Объёмная функция рассеяния b·β̃, 1/(м·ср), форма (…, 3)."""
        return self.b * phase_ff(cos_psi, self.n_ff, self.mu_ff)[..., None]

    def kd(self):
        """Диффузное ослабление рассеянного света сверху: K_d ≈ (a + b_b)/μ̄_d (Kirk 1984; оценка)."""
        return (self.a + self.bb_frac * self.b) / self.mu_d


class Lamp:
    def __init__(self, pos, axis, I0, rgb):
        self.pos = np.asarray(pos, float)
        self.axis = np.asarray(axis, float) / np.linalg.norm(axis)
        self.I0 = float(I0)
        self.rgb = np.asarray(rgb, float)

    def intensity(self, dirs):
        """Сила света в направлениях dirs (…, 3, единичные), кд, форма (…, 3)."""
        cos_t = np.maximum(dirs @ self.axis, 0.0)
        return (self.I0 * cos_t)[..., None] * self.rgb


def lamp_intensity_I0(p, lamp, power):
    """I0 = Φ/π (ламбертов излучатель); Φ линейно по мощности от значения при 50 %."""
    return p[lamp + "_flux_50"] * (power / 0.5) / np.pi


# ---------------- кадр ----------------

def ambient_irradiance(water, E_surf, depth, n_up):
    """Освещённость поверхности рассеянным светом сверху: E_d(z)·((1+n·up)/2 + R·(1−n·up)/2)."""
    Ed = np.asarray(E_surf, float) * np.exp(-water.kd() * depth[..., None])
    n_up = np.asarray(n_up)[..., None]
    return Ed * ((1 + n_up) / 2 + 0.05 * (1 - n_up) / 2)


def path_radiance_inf(water, E_surf, depth):
    """L∞ ≈ b·E₀/(4π·c), E₀ ≈ E_d/μ̄_d (изотропное приближение поля яркости; оценка)."""
    Ed = np.asarray(E_surf, float) * np.exp(-water.kd() * np.asarray(depth)[..., None])
    return water.b * Ed / water.mu_d / (4 * np.pi * water.c)


def backscatter(cam, dirs, D, lamp, water, n=2000):
    """∫₀ᴰ b β̃(ψ) I(θ)/r² exp(−c(r+t)) dt. dirs (N, 3), D (N,). Шаги сгущены к камере: t = D·s²."""
    dirs = np.atleast_2d(dirs)
    D = np.atleast_1d(D)
    s = (np.arange(n) + 0.5) / n
    t = D[:, None] * s[None, :] ** 2                     # (N, n)
    dt = D[:, None] * 2 * s[None, :] / n
    X = cam + dirs[:, None, :] * t[..., None]            # точки на луче
    v = X - lamp.pos
    r = np.linalg.norm(v, axis=-1)
    l = v / r[..., None]                                 # направление распространения света лампы
    cos_psi = -np.sum(l * dirs[:, None, :], axis=-1)     # угол между светом и направлением к камере
    I = lamp.intensity(l)
    f = water.beta(cos_psi) * I / (r ** 2)[..., None] * np.exp(-water.c * (r + t)[..., None])
    return np.sum(f * dt[..., None], axis=1)


def radiance(cam, dirs, D, normals, albedo, lamp, water, E_surf=(0, 0, 0), up=(0, 0, 1), depth_of=None, n=2000):
    """Яркость (N, 3) для лучей из cam в направлениях dirs до поверхности на дальности D.
    albedo (N, 3); depth_of(X) -> глубина точек (для рассеянного света сверху)."""
    dirs = np.atleast_2d(dirs)
    D = np.atleast_1d(D).astype(float)
    P = cam + dirs * D[:, None]
    v = P - lamp.pos
    r = np.linalg.norm(v, axis=-1)
    l = v / r[:, None]
    cos_i = np.maximum(-np.sum(l * normals, axis=-1), 0.0)
    E = lamp.intensity(l) * (cos_i / r ** 2)[:, None] * np.exp(-water.c * r[:, None])
    up = np.asarray(up, float)
    if depth_of is not None and np.any(E_surf):
        E = E + ambient_irradiance(water, E_surf, depth_of(P), normals @ up)
        Linf = path_radiance_inf(water, E_surf, depth_of(cam[None, :])[0])
    else:
        Linf = np.zeros(3)
    T = np.exp(-water.c * D[:, None])
    return albedo / np.pi * E * T + backscatter(cam, dirs, D, lamp, water, n) + Linf * (1 - T)


def srgb_encode(x):
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * x ** (1 / 2.4) - 0.055)


def srgb_decode(v):
    v = np.asarray(v, float)
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


def gray601(rgb):
    return 0.298936 * rgb[..., 0] + 0.587043 * rgb[..., 1] + 0.114021 * rgb[..., 2]
