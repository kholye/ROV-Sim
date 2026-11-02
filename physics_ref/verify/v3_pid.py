"""V3: удержание глубины против бассейна (Дунаев, рис. 48-49, т. 9).

Схема после калибровки (2026-11-02):
  - расход поршня и линейное затухание подогнаны по рис. 48 (calibrate_fig48.py);
  - рис. 49 (только P) и т. 9 (настроенный ПИД) в подгонке не участвуют: на них проверяется предсказание;
  - ПИД подбирается в симуляторе на сетке пульта (0,0-9,9 шаг 0,1), критерий ITAE на цели 1,5 м,
    с шумом датчика глубины как в бассейне; числа т. 9 в подборе не участвуют.
Критерии: (а) max отклонение не хуже чем вдвое от 0,05 / 0,02 / 0,027 м, без устойчивых колебаний;
(б) только P: амплитуда порядка метра на цели 2 м, период сопоставим с рис. 49.
"""
import itertools
import time

import numpy as np

from common import OUT, plt, save_results, verdict
from rov import params
from rov.sim import HeaveBatch, run_depth_hold

p = params.load()
NOISE = p["depth_noise_sigma"]
DT = 0.02
Z0 = 0.2
res = {"tuning": {}, "eval": {}, "p_only": {}, "sensitivity": {}}
measured = {0.5: 0.05, 1.5: 0.02, 2.0: 0.027}

# ---------- рис. 49: признаки из оцифровки ----------
f49 = np.loadtxt(OUT / "dunaev_fig49_digitized.csv", delimiter=",", skiprows=1)
win = 25
sm = np.convolve(f49[:, 1], np.ones(win) / win, mode="same")
core = slice(win, -win)
t49, z49 = f49[core, 0], sm[core]
tops = [t49[(t49 > a) & (t49 < b)][np.argmin(z49[(t49 > a) & (t49 < b)])] for a, b in ((40, 80), (150, 190))]
fig49 = {"max_dev_m": float(np.abs(f49[:, 1] - 2.0).max()), "period_s": float(tops[1] - tops[0]),
         "note": "период по двум верхним точкам (сглаживание 5 с), амплитуда как max |z − 2| по сырой оцифровке"}
res["fig49"] = fig49


def metrics(out, target):
    t, z = out[:, 0], out[:, 1]
    e = z - target
    cross = np.where(np.sign(e[1:]) != np.sign(e[:-1]))[0]
    t_reach = t[cross[0] + 1] if len(cross) else None
    m = {"t_reach_s": t_reach}
    if t_reach is not None:
        w = (t >= t_reach) & (t <= t_reach + 20)
        m["max_dev_first20s_m"] = float(np.abs(e[w]).max())
        m["mean_first20s_m"] = float(z[w].mean())
    ss = t >= t[-1] - 100
    m["max_dev_last100s_m"] = float(np.abs(e[ss]).max())
    m["ptp_last100s_m"] = float(np.ptp(z[ss]))
    m["mean_last100s_m"] = float(z[ss].mean())
    m["max_depth_m"] = float(z.max())
    m["hits_pool_bottom_3m"] = bool(z.max() > 3.0 - 0.07)
    if len(cross) > 2:
        m["period_s"] = float(2 * np.mean(np.diff(t[cross[1:] + 1])))
    return m


# ---------- подбор ПИД ----------
t0 = time.time()
hb = HeaveBatch(p)
coarse = [0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0, 1.5, 2.0, 3.0, 5.0, 7.0, 9.9]
G = np.array(list(itertools.product(coarse, coarse, coarse)))
SEEDS = (11, 12, 13)


def itae(P):
    """ITAE, усреднённый по трём реализациям шума датчика (иначе подбор подстраивается под один шум)."""
    return np.mean([hb.run(P[:, 0], P[:, 1], P[:, 2], 1.5, 300.0, DT, Z0, depth_noise=NOISE, seed=s) for s in SEEDS], axis=0)


J = itae(G)
best, best_J = G[np.argmin(J)], J.min()
for it in range(20):
    rng_ = [np.clip(np.round(best[i] + np.arange(-3, 4) * 0.1, 1), 0.0, 9.9) for i in range(3)]
    L = np.unique(np.array(list(itertools.product(*rng_))), axis=0)
    JL = itae(L)
    if JL.min() >= best_J - 1e-12:
        break
    best, best_J = L[np.argmin(JL)], JL.min()
kp, ki, kd = (float(np.round(v, 1)) for v in best)
res["tuning"] = {"criterion": f"ITAE 0-300 с, цель 1,5 м, старт с 0,2 м, шум датчика {NOISE*1000:.0f} мм, среднее по 3 реализациям шума",
                 "best": {"Kp": kp, "Ki": ki, "Kd": kd, "ITAE": float(best_J)}, "seconds": time.time() - t0}
print("ПИД:", kp, ki, kd, flush=True)

# ---------- (а) т. 9: полная модель, шум датчика, другая реализация шума ----------
fig, ax = plt.subplots(2, 2, figsize=(13, 8))
runs = {}
for target in (0.5, 1.5, 2.0):
    out = run_depth_hold(p, target, kp, ki, kd, 300.0, DT, Z0, depth_noise=NOISE, seed=3)
    runs[target] = out
    m = metrics(out, target)
    lim = 2 * measured[target]
    m.update(measured_max_dev_m=measured[target], criterion_m=lim,
             ok_first20s=bool(m.get("max_dev_first20s_m", 9) <= lim), ok_steady=bool(m["max_dev_last100s_m"] <= lim))
    res["eval"][str(target)] = m
    ax[0, 0].plot(out[:, 0], out[:, 1], label=f"цель {target} м")
    ax[0, 0].axhline(target, color="k", lw=0.5, ls=":")
ax[0, 0].invert_yaxis()
ax[0, 0].set(title=f"(а) ПИД с сетки пульта: Kp {kp}, Ki {ki}, Kd {kd} (полная модель, шум {NOISE*1000:.0f} мм)",
             xlabel="t, с", ylabel="истинная глубина, м")
ax[0, 0].legend(fontsize=8)
for target, out in runs.items():
    ax[0, 1].plot(out[:, 0], (out[:, 1] - target) * 100, lw=0.8, label=f"{target} м")
for target in measured:
    ax[0, 1].axhspan(-200 * measured[target], 200 * measured[target], alpha=0.05)
ax[0, 1].set_ylim(-15, 15)
ax[0, 1].set(title="ошибка (полосы: удвоенное измеренное отклонение т. 9)", xlabel="t, с", ylabel="z − цель, см")
ax[0, 1].legend(fontsize=8)

# ---------- (б) рис. 49: только P ----------
KPs = np.round(np.arange(0.1, 10.0, 0.1), 1)
_, rec = hb.run(KPs, np.zeros_like(KPs), np.zeros_like(KPs), 2.0, 600.0, DT, Z0, record=True, depth_noise=NOISE, seed=5)
amp = []
for j in range(len(KPs)):
    e = rec[:, j] - 2.0
    cross = np.where(np.sign(e[1:]) != np.sign(e[:-1]))[0]
    amp.append(float(np.abs(e[cross[0] + 1:]).max()) if len(cross) else np.nan)
amp = np.array(amp)
out_p = run_depth_hold(p, 2.0, 1.0, 0.0, 0.0, 600.0, DT, Z0, depth_noise=NOISE, seed=5)
mp = metrics(out_p, 2.0)
res["p_only"] = {"Kp": KPs.tolist(), "max_dev_after_reach_m": amp.tolist(),
                 "range_m": [float(np.nanmin(amp)), float(np.nanmax(amp))], "full_model_Kp1": mp,
                 "fig49_max_dev_m": fig49["max_dev_m"], "fig49_period_s": fig49["period_s"]}
ax[1, 0].plot(KPs, amp, "o-", ms=3, label="модель")
ax[1, 0].axhline(fig49["max_dev_m"], color="r", ls=":", label=f"рис. 49: {fig49['max_dev_m']:.2f} м")
ax[1, 0].set(title="(б) только P, цель 2 м: max отклонение после выхода на цель", xlabel="Kp (Ki = Kd = 0)", ylabel="м")
ax[1, 0].set_ylim(0, 1.5)
ax[1, 0].legend(fontsize=8)
# наложение: модель сдвинута по времени так, чтобы её нижняя точка совпала с нижней точкой рис. 49
tm, zm = out_p[:, 0], out_p[:, 1]
sel = tm > 150
t_low_m = tm[sel][np.argmax(zm[sel])]
t_low_r = f49[np.argmax(f49[:, 1]), 0]
shift = t_low_r - t_low_m
ax[1, 1].plot(f49[:, 0], f49[:, 1], "b", lw=0.8, label="рис. 49 Дунаева (оцифровка)")
w = (tm + shift >= f49[0, 0]) & (tm + shift <= f49[-1, 0])
ax[1, 1].plot(tm[w] + shift, zm[w], "r--", label=f"модель, Kp = 1, сдвиг {shift:.0f} с")
ax[1, 1].axhline(2.0, color="k", lw=0.5, ls=":")
ax[1, 1].invert_yaxis()
ax[1, 1].set(title=f"(б) только P: период модели {mp.get('period_s', float('nan')):.0f} с, рис. 49 ≈ {fig49['period_s']:.0f} с",
             xlabel="t, с", ylabel="глубина, м")
ax[1, 1].legend(fontsize=8)
fig.tight_layout()
fig.savefig(OUT / "v3_pid.png")

# ---------- чувствительность (те же коэффициенты) ----------
for name, kw in {"без шума датчика": dict(depth_noise=0.0), "шум датчика 5 мм": dict(depth_noise=0.005),
                 "прогноз Дунаева T = 12 с": dict(depth_noise=NOISE, predict_T=12.0)}.items():
    res["sensitivity"][name] = metrics(run_depth_hold(p, 1.5, kp, ki, kd, 300.0, DT, Z0, seed=3, **kw), 1.5)
for vn, q, c in ((40e-6, 0.83e-6, 4.30), (100e-6, 2.14e-6, 15.01)):
    pp = params.load(neutral_tank_volume=vn, tank_rate=q, heave_damping_lin=c)
    name = f"нейтральность {vn*1e6:.0f} мл (перекалибровано: {q*1e6:.2f} мл/с, {c:.1f} Н·с/м)"
    res["sensitivity"][name] = metrics(run_depth_hold(pp, 1.5, kp, ki, kd, 300.0, DT, Z0, depth_noise=NOISE, seed=3), 1.5)
    res["sensitivity"][name]["p_only_2m"] = metrics(run_depth_hold(pp, 2.0, 1.0, 0, 0, 600.0, DT, Z0, depth_noise=NOISE, seed=5), 2.0)

# Дунаев 4.1: запись включали после достижения глубины (по отметкам на трубе), то есть в установившемся
# режиме. Поэтому критерий (а) по последним 100 с; перелёт на подходе (first20s) только для сведения.
ok_a = all(res["eval"][k]["ok_steady"] for k in res["eval"])
per = mp.get("period_s", np.nan)
ok_b = bool(0.5 <= np.nanmax(amp) / fig49["max_dev_m"] <= 2.0 and 0.5 <= per / fig49["period_s"] <= 2.0)
res["verdict_a"], res["verdict_b"] = ok_a, ok_b
save_results("v3", res)
print({k: {kk: round(vv, 3) if isinstance(vv, float) else vv for kk, vv in v.items()} for k, v in res["eval"].items()})
print("P:", res["p_only"]["range_m"], "период", per, "| рис.49", fig49)
for k, v in res["sensitivity"].items():
    print(k, round(v["max_dev_last100s_m"], 3), v.get("p_only_2m", {}).get("period_s"))
print("V3(а):", verdict(ok_a), " V3(б):", verdict(ok_b))
