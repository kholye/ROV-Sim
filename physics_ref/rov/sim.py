"""Прогоны полной модели: шаг физики dt, бортовое управление с периодом control_period."""
import numpy as np

from . import dynamics as dyn
from .control import DepthPID
from .environment import Battery


def run_depth_hold(p, target, kp, ki, kd, t_end, dt=0.01, z0=0.0, predict_T=0.0,
                   depth_noise=0.0, seed=1, x0=None, thr=(0.0, 0.0)):
    """Удержание глубины: обе цистерны получают одну команду ПИД (как синхронная работа)."""
    veh = dyn.Vehicle(p)
    rng = np.random.default_rng(seed)
    pid = DepthPID(kp, ki, kd, p, predict_T)
    bat = Battery(p)
    x = dyn.initial_state(z0) if x0 is None else x0.copy()
    n_ctrl = int(round(p["control_period"] / dt))
    n = int(round(t_end / dt))
    cmd = 0
    out = np.zeros((n + 1, 6))
    for i in range(n + 1):
        t = i * dt
        if i % n_ctrl == 0:
            h = x[2] + depth_noise * rng.standard_normal()
            cmd = pid.update(target, h)
        out[i] = (t, x[2], x[4], x[12], x[13], cmd)
        if i == n:
            break
        x, _ = dyn.rk4_step(veh, x, dt, thr, (cmd, cmd))
        bat.step(dt, thr, (cmd, cmd))
    return out


class HeaveBatch:
    """Только вертикаль, векторно по многим наборам ПИД сразу (для подбора коэффициентов).

    Без плоскостей при V1 = V2 и нулевых углах уравнения 6 ст. св. сводятся ровно к этому:
      (m + rho(V1+V2) + Z_w') w' = W - B f(z) - d_w |w| w - c_w w
    Совпадение с полной моделью проверяется в tests/test_model.py (TestHeave).
    """

    def __init__(self, p):
        self.p = p
        veh = dyn.Vehicle(p)
        self.Zw = veh.MA[2, 2]
        # сопротивление плоскостей с нормалью z при чистой вертикали (подъёмной силы нет, u = 0);
        # их момент по дифференту здесь не учтён, поэтому с плоскостями это приближение
        self.dw = veh.d_quad[2] + sum(0.5 * p["rho"] * f["area"] * f["cd_plate"] for f in p["fins"] if f["normal"] == 2)
        self.r = veh.r
        self.cw = p["heave_damping_lin"]
        self.Bfull = p["rho"] * p["g"] * veh.displaced_volume(False)

    def frac(self, z):
        r = self.r
        h = np.clip(z + r, 0.0, 2 * r)
        seg = r * r * np.arccos(np.clip((r - h) / r, -1, 1)) - (r - h) * np.sqrt(np.maximum(2 * r * h - h * h, 0))
        return seg / (np.pi * r * r)

    def acc(self, z, w, Vt):
        p = self.p
        m = p["mass_dry"] + p["rho"] * Vt
        F = m * p["g"] - self.Bfull * self.frac(z) - self.dw * np.abs(w) * w - self.cw * w
        return F / (m + self.Zw)

    def run(self, KP, KI, KD, target, t_end, dt=0.01, z0=0.0, predict_T=0.0, record=False,
            depth_noise=0.0, seed=1):
        p = self.p
        KP, KI, KD = (np.asarray(k, dtype=float) for k in (KP, KI, KD))
        nset = KP.size
        z = np.full(nset, z0)
        w = np.zeros(nset)
        Vt = np.full(nset, 2 * 35e-6)       # обе цистерны вместе
        cap = 2 * p["tank_capacity"]
        rate = 2 * p["tank_rate"]
        integ = np.zeros(nset)
        prev = None
        prev_h = None
        prev_v = np.zeros(nset)
        cmd = np.zeros(nset)
        n_ctrl = int(round(p["control_period"] / dt))
        cdt = p["control_period"]
        n = int(round(t_end / dt))
        itae = np.zeros(nset)
        rec = [] if record else None
        rng = np.random.default_rng(seed)
        for i in range(n):
            t = i * dt
            if i % n_ctrl == 0:
                h = z + depth_noise * rng.standard_normal(nset) if depth_noise > 0 else z
                v = np.zeros(nset) if prev_h is None else (h - prev_h) / cdt
                a = (v - prev_v) / cdt
                prev_h, prev_v = h.copy(), v
                h_eff = h + v * predict_T + a * predict_T ** 2 / 2 if predict_T > 0 else h
                e = target - h_eff
                integ = np.clip(integ + e * cdt, -p["pid_integral_limit"], p["pid_integral_limit"])
                de = np.zeros(nset) if prev is None else (e - prev) / cdt
                prev = e
                u = KP * e + KI * integ + KD * de
                cmd = np.where(u > p["pid_threshold"], 1.0, np.where(u < -p["pid_threshold"], -1.0, 0.0))
            if record:
                rec.append(z.copy())
            itae += t * np.abs(target - z) * dt
            # RK4 по (z, w); объём цистерн меняется линейно на шаге
            Vdot = rate * cmd * (((cmd > 0) & (Vt < cap)) | ((cmd < 0) & (Vt > 0)))
            k1z, k1w = w, self.acc(z, w, Vt)
            k2z, k2w = w + 0.5 * dt * k1w, self.acc(z + 0.5 * dt * k1z, w + 0.5 * dt * k1w, Vt + 0.5 * dt * Vdot)
            k3z, k3w = w + 0.5 * dt * k2w, self.acc(z + 0.5 * dt * k2z, w + 0.5 * dt * k2w, Vt + 0.5 * dt * Vdot)
            k4z, k4w = w + dt * k3w, self.acc(z + dt * k3z, w + dt * k3w, Vt + dt * Vdot)
            z = z + dt / 6 * (k1z + 2 * k2z + 2 * k3z + k4z)
            w = w + dt / 6 * (k1w + 2 * k2w + 2 * k3w + k4w)
            Vt = np.clip(Vt + dt * Vdot, 0.0, cap)
        return (itae, np.array(rec)) if record else itae
