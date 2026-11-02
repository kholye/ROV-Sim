"""Датчики: давление (глубина), сырые гироскопы и акселерометры с шумом по Аллану, модель модуля AHRS.

Шум по Дунаеву (т. 5-6): N случайное блуждание угла/скорости, K случайное блуждание
скорости/ускорения, B нестабильность нуля. Дискретная модель на частоте fs (IEEE Std 952):
  белый шум      СКО = N * sqrt(fs)
  блуждание нуля b_k+1 = b_k + K * sqrt(dt) * w
  нестабильность Гаусс-Марков с СКО B/0.62 и временем tau (минимум кривой Аллана ~ B)
"""
import numpy as np

DEG = np.pi / 180.0


def depth_from_pressure(p_pa, p):
    return (p_pa - p["p_atm"]) / (p["rho"] * p["g"])


def pressure_at(depth, p):
    return p["p_atm"] + p["rho"] * p["g"] * depth


def imu_noise(n, fs, N, K, B, tau, rng, bias0=None):
    """Аддитивная ошибка одной оси длиной n отсчётов."""
    dt = 1.0 / fs
    white = N * np.sqrt(fs) * rng.standard_normal(n)
    rrw = np.cumsum(K * np.sqrt(dt) * rng.standard_normal(n))
    sig_gm = B / 0.62
    a = np.exp(-dt / tau)
    q = sig_gm * np.sqrt(1 - a * a)
    w = rng.standard_normal(n)
    gm = np.empty(n)
    g = sig_gm * rng.standard_normal() if bias0 is None else bias0
    for i in range(n):
        g = a * g + q * w[i]
        gm[i] = g
    return white + rrw + gm


def allan_deviation(y, fs, taus):
    """Перекрывающаяся девиация Аллана по ф. (56)-(57) Дунаева (через накопленный угол)."""
    theta = np.concatenate([[0.0], np.cumsum(y) / fs])
    M = len(y)
    out = []
    for tau in taus:
        m = int(round(tau * fs))
        if m < 1 or 2 * m >= M:
            out.append(np.nan)
            continue
        d = theta[2 * m:] - 2 * theta[m:-m] + theta[:-2 * m]
        out.append(np.sqrt(np.sum(d * d) / (2.0 * (tau ** 2) * len(d))))
    return np.array(out)


def ahrs_heading(psi_true, gyro_z, fs, tau_f, mag_sigma, rng, psi0=None):
    """Курс модуля: интеграл гироскопа + комплементарная поправка по магнитометру.

    tau_f = 0 или inf: только гироскоп (без магнитометра).
    Устройство фильтра внутри SSAH-RS220 не известно, это модель-оценка.
    """
    n = len(gyro_z)
    dt = 1.0 / fs
    est = np.empty(n)
    psi = psi_true[0] if psi0 is None else psi0
    use_mag = np.isfinite(tau_f) and tau_f > 0
    k = dt / tau_f if use_mag else 0.0
    mag = psi_true + mag_sigma * rng.standard_normal(n)
    for i in range(n):
        psi += gyro_z[i] * dt
        if use_mag:
            e = np.arctan2(np.sin(mag[i] - psi), np.cos(mag[i] - psi))
            psi += k * e
        est[i] = psi
    return est
