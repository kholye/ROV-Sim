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


def radiance(cam, dirs, D, normals, albedo, lamp, water, E_surf=(0, 0, 0), up=(0, 0, 1), depth_of=None, n=2000,
             silt=None):
    """Яркость (N, 3) для лучей из cam в направлениях dirs до поверхности на дальности D.
    albedo (N, 3); depth_of(X) -> глубина точек (для рассеянного света сверху); silt — SiltCloud или None."""
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
    path = backscatter(cam, dirs, D, lamp, water, n) + Linf * (1 - T)
    if silt:
        Tc, Tk, S = silt_terms(cam, dirs, D, silt, up, lamp, water, E_surf, depth_of)
        # размытая часть: освещённость гладкой поверхности, обращённой к камере (без рельефа и рисунка)
        E_blur = lamp.intensity(l) * (np.maximum(np.sum(l * dirs, axis=-1), 0.0) / r ** 2)[:, None] \
            * np.exp(-water.c * r[:, None])
        if depth_of is not None and np.any(E_surf):
            E_blur = E_blur + ambient_irradiance(water, E_surf, depth_of(P), np.zeros(len(D)))
        return (albedo * Tc * E + SILT_BLUR_ALBEDO * (Tk - Tc) * E_blur) / np.pi * T + path * Tk + S
    return albedo / np.pi * E * T + path


SILT_BLUR_ALBEDO = 0.15   # рисунок поверхности за облаком размыт: в рассеянной вперёд части — среднее альбедо (как у замера экспозиции)


# ---------------- облако ила (разд. 29) ----------------

def silt_star(p):
    """Поглощение и рассеяние на массу ила в каналах R, G, B, м²/кг: a*(λ) = a*(443)·exp(−S(λ − 443)) в центре
    полосы камеры, b* постоянно по спектру (Babin и др. 2003; Babin, Stramski 2004)."""
    lam = np.array(p["camera_band_nm"], float)
    a = p["silt_a_star_443"] * np.exp(-p["silt_a_slope"] * (lam - 443.0))
    b = np.full(3, float(p["silt_b_star"]))
    return a, b


class SiltCloud:
    """Клубы ила для света: центры C (n, 3), массы m (кг), σ по горизонтали sh и по вертикали sv (м), уровень дна
    bed (координата вдоль up) — отражение от дна; a_star, b_star — из silt_star."""

    def __init__(self, C, m, sh, sv, bed, a_star, b_star):
        self.C = np.atleast_2d(np.asarray(C, float))
        self.m = np.atleast_1d(np.asarray(m, float))
        self.sh = np.atleast_1d(np.asarray(sh, float))
        self.sv = np.atleast_1d(np.asarray(sv, float))
        self.bed = np.atleast_1d(np.asarray(bed, float))
        self.a_star = np.asarray(a_star, float)
        self.b_star = np.asarray(b_star, float)

    def __bool__(self):
        return len(self.m) > 0


def _sdot(u, w, up, sh, sv):
    """Скалярное произведение в метрике клуба: горизонтальные части / σh², вертикальные / σv²."""
    uv = u @ up
    wv = w @ up
    return (np.sum(u * w, axis=-1) - uv * wv) / sh ** 2 + uv * wv / sv ** 2


def silt_line(cam, dirs, D, C, m, sh, sv, bed, up):
    """∫₀ᴰ c(t) dt (кг/м²) вдоль лучей для одного клуба с отражением от дна; точная формула через erf.
    Возвращает интеграл, точку луча t*, ближайшую к центру в метрике клуба (в [0, D]), и 1/a — СКО клуба вдоль луча."""
    from scipy.special import erf
    up = np.asarray(up, float)
    norm = m / ((2 * np.pi) ** 1.5 * sh ** 2 * sv)
    tot = np.zeros(len(D))
    t_star = None
    s_along = None
    for center in (C, C + 2.0 * (bed - C @ up) * up):
        q0 = cam - center
        a2 = _sdot(dirs, dirs, up, sh, sv)
        qw = _sdot(dirs, np.broadcast_to(q0, dirs.shape), up, sh, sv)
        q2 = _sdot(q0, q0, up, sh, sv)
        a = np.sqrt(a2)
        t0 = -qw / a2
        d2 = np.maximum(q2 - qw * qw / a2, 0.0)
        tot += norm * np.exp(-0.5 * d2) * np.sqrt(np.pi / 2) / a * (
            erf(a * (D - t0) / np.sqrt(2)) + erf(a * t0 / np.sqrt(2)))
        if t_star is None:
            t_star = np.clip(t0, 0.0, D)
            s_along = 1.0 / a
    return tot, t_star, s_along


def silt_terms(cam, dirs, D, cloud, up, lamp, water, E_surf=(0, 0, 0), depth_of=None):
    """Облако ила на луче: пропускание T_s (N, 3) и добавка яркости S (N, 3).

    Для клуба i: M_i — интеграл концентрации вдоль луча (кг/м²). Возвращает (T_c, T_k, S).
    Чёткое изображение сквозь облако гаснет как T_c = exp(−Σ (a* + b*)·M_i) (несёт рисунок поверхности).
    Свет, рассеянный облаком вперёд, из пучка не уходит (рассеяние ила сильно вытянуто вперёд), но рисунок
    размывает: яркость за облаком гаснет как T_k = exp(−Σ k·M_i), а в части T_k − T_c вместо альбедо поверхности
    берётся среднее SILT_BLUR_ALBEDO, а освещённость — как у гладкой поверхности, обращённой к камере (radiance). Пелена воды за облаком гаснет как T_k (она гладкая; пелена перед
    облаком тоже ослабляется — приближение). Свет, рассеянный облаком к камере, — квазиоднократное приближение
    (Gordon 1973): рассеяние вперёд не выводит свет из пучка, путь туда и обратно гаснет с k = a* + B·b*
    (B — доля рассеяния назад), поэтому S_i = b*/(2k)·(1 − e^(−2k·M_i))·[β̃(ψ)·I(l)/r²·e^(−c(r+t))
    + E_d(P)/(4π μ̄_d)·e^(−c t)]; освещённость E — одна на луч, в точке t̄ = Σ M_i t_i / Σ M_i (t_i — точка луча,
    ближайшая к центру клуба i; так шейдер считает её раз, а не на каждый клуб); сглаживание по протяжённости облака
    вдоль луча s² = Σ M_i (t_i² + σ_i²)/Σ M_i − t̄²: 1/r² -> 1/(r² + s²), угол рассеяния не меньше atan(s/r). Тонкое облако: S = b*·M·β̃·E
    (однократное рассеяние); толстое — b*·β̃/(2k)·E: яркость на единицу освещённости 0,03-0,05 1/ср, как
    у мутной воды по Gordon и др. 1988 (≈ 0,0949·u + 0,0794·u², u = b_b/(a + b_b))."""
    dirs = np.atleast_2d(dirs)
    D = np.atleast_1d(D).astype(float)
    up = np.asarray(up, float)
    c_star = cloud.a_star + cloud.b_star
    k = cloud.a_star + water.bb_frac * cloud.b_star
    tau = np.zeros((len(D), 3))
    tau_k = np.zeros((len(D), 3))
    sat = np.zeros((len(D), 3))
    Msum = np.zeros(len(D))
    tM = np.zeros(len(D))
    tM2 = np.zeros(len(D))
    for i in range(len(cloud.m)):
        M, t, sa = silt_line(cam, dirs, D, cloud.C[i], cloud.m[i], cloud.sh[i], cloud.sv[i], cloud.bed[i], up)
        tau += M[:, None] * c_star
        tau_k += M[:, None] * k
        sat += cloud.b_star / (2 * k) * (1.0 - np.exp(-2 * k * M[:, None]))
        Msum += M
        tM += M * t
        tM2 += M * (t * t + sa * sa)
    # освещённость облака — одна на луч: в средней по массе точке клубов на луче, сглаженная по протяжённости
    # облака вдоль луча s (СКО): r² -> r² + s², угол рассеяния не меньше atan(s/r) (облако не точка у лампы)
    Mpos = np.maximum(Msum, 1e-30)
    t = np.where(Msum > 0, tM / Mpos, 0.0)
    s2 = np.where(Msum > 0, np.maximum(tM2 / Mpos - t * t, 0.0), 0.0)
    P = cam + dirs * t[:, None]
    v = P - lamp.pos
    r = np.maximum(np.linalg.norm(v, axis=-1), 0.02)
    l = v / r[:, None]
    re2 = r * r + s2
    cos_psi = np.minimum(-np.sum(l * dirs, axis=-1), r / np.sqrt(re2))
    Ein = phase_ff(cos_psi, water.n_ff, water.mu_ff)[:, None] * lamp.intensity(l) / re2[:, None] \
        * np.exp(-water.c * (r + t)[:, None])
    if depth_of is not None and np.any(E_surf):
        Ed = np.asarray(E_surf, float) * np.exp(-water.kd() * depth_of(P)[:, None])
        Ein = Ein + Ed / (4 * np.pi * water.mu_d) * np.exp(-water.c * t[:, None])
    S = sat * Ein
    return np.exp(-tau), np.exp(-tau_k), S


def srgb_encode(x):
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * x ** (1 / 2.4) - 0.055)


def srgb_decode(v):
    v = np.asarray(v, float)
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


def gray601(rgb):
    return 0.298936 * rgb[..., 0] + 0.587043 * rgb[..., 1] + 0.114021 * rgb[..., 2]
