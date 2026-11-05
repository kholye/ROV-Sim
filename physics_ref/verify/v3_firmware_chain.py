"""V3 с цепочкой датчика и регулятора прошивки (Павлов, прил. А) против упрощённой схемы этапа 2.

Цепочка прошивки: глубина = АЦП 10 бит, шаг 10,7 мм; скорость = среднее по 10 разностям за 0,1 с;
ускорение = разность средних скоростей / 0,1 с; ошибка с прогнозом h + 12·v + 72·a; предел интеграла 0,5; порог 0,005.
Варианты:
  base   — как в V3 (шум 2 мм, прогноза нет), коэффициенты V3;
  fw     — цепочка прошивки, те же коэффициенты;
  fw_def — цепочка прошивки, коэффициенты по умолчанию прошивки (Kp 1, Ki 0, Kd 0);
  fw_tun — цепочка прошивки, коэффициенты подобраны ITAE на сетке пульта (грубая сетка);
  fw_bug — как fw_tun, но ветка «стоп» заменена на «набрать воду» (так читается `else if (cmd = -1)` в pid()).
Критерии как в V3: отклонение в установившемся режиме (последние 100 с) не хуже удвоенного измеренного в т. 9
(0,05 / 0,02 / 0,027 м); только P на цели 2 м — размах и период рис. 49.
Это проверка согласованности, не валидация: версия прошивки в опытах Дунаева не известна.
"""
import itertools

import numpy as np

from common import OUT, plt, save_results
from rov import params
from rov.sim import HeaveBatch

p = params.load()
hb = HeaveBatch(p)
DT = 0.02
Z0 = 0.2
MEAS = {0.5: 0.05, 1.5: 0.02, 2.0: 0.027}
Q = 0.0107                              # шаг АЦП глубины, м


class Sense:
    """Измерение глубины и производные так, как считает прошивка (раз в 0,1 с)."""

    def __init__(self, n, fw, noise, rng, phase):
        self.fw, self.noise, self.rng, self.n = fw, noise, rng, n
        self.phase = phase                          # смещение нуля АЦП относительно истинной глубины, м
        self.last = None
        self.dv = np.zeros((10, n))
        self.vbar = np.zeros(n)

    def update(self, z):
        h = z + self.noise * self.rng.standard_normal(self.n) if self.noise > 0 else z.copy()
        if not self.fw:
            v = np.zeros(self.n) if self.last is None else (h - self.last) / 0.1
            a = (v - getattr(self, "_pv", np.zeros(self.n))) / 0.1
            self._pv = v
            self.last = h.copy()
            return h, v, a
        h = np.round((h + self.phase) / Q) * Q - self.phase   # квантование с неизвестной фазой
        d = np.zeros(self.n) if self.last is None else (h - self.last) * 10.0
        self.last = h.copy()
        self.dv = np.vstack([d[None], self.dv[:-1]])
        vb = self.dv.mean(axis=0)
        a = (vb - self.vbar) * 10.0
        self.vbar = vb
        return h, vb, a


def run(KP, KI, KD, target, t_end, fw, T, noise, seed, bug=False, record=False):
    KP, KI, KD = (np.asarray(k, float) for k in (KP, KI, KD))
    n = KP.size
    rng = np.random.default_rng(seed)
    sense = Sense(n, fw, noise, rng, rng.uniform(0, Q, n))
    z = np.full(n, Z0)
    w = np.zeros(n)
    Vt = np.full(n, 2 * 35e-6)
    cap, rate = 2 * p["tank_capacity"], 2 * p["tank_rate"]
    integ = np.zeros(n)
    prev = None
    cmd = np.zeros(n)
    nc = int(round(p["control_period"] / DT))
    nstep = int(round(t_end / DT))
    itae = np.zeros(n)
    rec = []
    for i in range(nstep):
        t = i * DT
        if i % nc == 0:
            h, v, a = sense.update(z)
            h_eff = h + v * T + a * T ** 2 / 2 if T > 0 else h
            e = target - h_eff
            integ = np.clip(integ + e * 0.1, -p["pid_integral_limit"], p["pid_integral_limit"])
            de = np.zeros(n) if prev is None else (e - prev) / 0.1
            prev = e
            u = KP * e + KI * integ + KD * de
            if bug:
                cmd = np.where(u < -p["pid_threshold"], -1.0, 1.0)
            else:
                cmd = np.where(u > p["pid_threshold"], 1.0, np.where(u < -p["pid_threshold"], -1.0, 0.0))
        rec.append(z.copy())
        itae += t * np.abs(target - z) * DT
        Vdot = rate * cmd * (((cmd > 0) & (Vt < cap)) | ((cmd < 0) & (Vt > 0)))
        k1z, k1w = w, hb.acc(z, w, Vt)
        k2z, k2w = w + 0.5 * DT * k1w, hb.acc(z + 0.5 * DT * k1z, w + 0.5 * DT * k1w, Vt + 0.5 * DT * Vdot)
        k3z, k3w = w + 0.5 * DT * k2w, hb.acc(z + 0.5 * DT * k2z, w + 0.5 * DT * k2w, Vt + 0.5 * DT * Vdot)
        k4z, k4w = w + DT * k3w, hb.acc(z + DT * k3z, w + DT * k3w, Vt + DT * Vdot)
        z = z + DT / 6 * (k1z + 2 * k2z + 2 * k3z + k4z)
        w = w + DT / 6 * (k1w + 2 * k2w + 2 * k3w + k4w)
        Vt = np.clip(Vt + DT * Vdot, 0.0, cap)
    return itae, np.array(rec)


def steady_dev(rec, target):
    return np.abs(rec[-int(100 / DT):] - target).max(axis=0)


def tune(fw, T, bug=False):
    grid = [0.0, 0.1, 0.3, 0.5, 1.0, 2.0, 5.0, 9.9]
    G = np.array(list(itertools.product(grid, [0.0, 0.1, 0.5, 1.0], grid)))      # Kp, Ki, Kd
    J = np.mean([run(G[:, 0], G[:, 1], G[:, 2], 1.5, 300.0, fw, T, 0.002, s, bug)[0] for s in (11, 12)], axis=0)
    return G[np.argmin(J)], float(J.min())


variants = {}
cases = {"base": ((0.2, 0.0, 5.1), False, 0.0, False), "fw": ((0.2, 0.0, 5.1), True, 12.0, False),
         "fw_def": ((1.0, 0.0, 0.0), True, 12.0, False)}
for name, (k, fw, T, bug) in cases.items():
    variants[name] = {"K": k, "fw": fw, "T": T, "bug": bug}
for name, bug in (("fw_tun", False), ("fw_bug", True)):
    k, J = tune(True, 12.0, bug)
    variants[name] = {"K": tuple(float(x) for x in k), "fw": True, "T": 12.0, "bug": bug, "ITAE": J}
    print(name, "подобрано", k, "ITAE", round(J, 3), flush=True)

res = {"variants": {}}
fig, ax = plt.subplots(1, 3, figsize=(15, 4))
for name, v in variants.items():
    K = [np.array([x]) for x in v["K"]]
    row = {"K": v["K"], "bug": v["bug"], "T": v["T"], "fw": v["fw"]}
    for j, target in enumerate((0.5, 1.5, 2.0)):
        devs = [float(steady_dev(run(*K, target, 300.0, v["fw"], v["T"], 0.002, s, v["bug"])[1], target)[0]) for s in (3, 4, 5)]
        row[f"dev_{target}"] = {"median_m": float(np.median(devs)), "limit_m": 2 * MEAS[target], "ok": bool(np.median(devs) <= 2 * MEAS[target])}
        if s_plot := (target == 1.5):
            rec = run(*K, target, 300.0, v["fw"], v["T"], 0.002, 3, v["bug"])[1][:, 0]
            ax[0].plot(np.arange(len(rec)) * DT, rec, lw=0.8, label=name)
    ritae, rec = run(*K, 2.0, 600.0, v["fw"], v["T"], 0.002, 5, v["bug"])
    z = rec[:, 0]
    cross = np.where(np.sign(z[1:] - 2.0) != np.sign(z[:-1] - 2.0))[0]
    row["p_only_2m"] = {"max_dev_m": float(np.abs(z[cross[0]:] - 2.0).max()) if len(cross) else None}
    if v["K"][1] == 0 and v["K"][2] == 0:
        pass
    res["variants"][name] = row
    print(name, {k: (round(x["median_m"], 3), x["ok"]) for k, x in row.items() if k.startswith("dev_")}, flush=True)
ax[0].invert_yaxis()
ax[0].set(title="цель 1,5 м (одна реализация шума)", xlabel="t, с", ylabel="глубина, м")
ax[0].legend(fontsize=7)

# только P (рис. 49): размах и период для цепочки прошивки, Kp 1 и подобранный на сетке
for name, K in (("base", 1.0), ("fw", 1.0)):
    v = variants[name]
    _, rec = run([K], [0.0], [0.0], 2.0, 600.0, v["fw"], v["T"], 0.002, 5)
    z = rec[:, 0]
    cross = np.where(np.sign(z[1:] - 2.0) != np.sign(z[:-1] - 2.0))[0]
    period = float(2 * np.mean(np.diff(cross[1:]) * DT)) if len(cross) > 3 else None
    res.setdefault("p_only_kp1", {})[name] = {"max_dev_m": float(np.abs(z[cross[0]:] - 2.0).max()) if len(cross) else None,
                                              "period_s": period, "fig49": {"max_dev_m": 0.96, "period_s": 115}}
    ax[1].plot(np.arange(len(z)) * DT, z, lw=0.8, label=name)
ax[1].invert_yaxis()
ax[1].set(title="только P, Kp = 1, цель 2 м", xlabel="t, с")
ax[1].legend(fontsize=7)
ax[2].axis("off")
fig.tight_layout()
fig.savefig(OUT / "v3_firmware_chain.png")
save_results("v3_firmware_chain", res)
print(res["p_only_kp1"])
