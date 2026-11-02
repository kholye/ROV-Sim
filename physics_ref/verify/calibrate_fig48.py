"""Калибровка вертикали по рис. 48 Дунаева (всплытие со дна на 0,5 м).

Подгоняются только неизвестные числа: расход поршня q (на одну цистерну) и линейное
затухание по вертикали c (трос, трение). Нейтральность 70 мл взята из кода Дунаева.
Участок 0-78 с: аппарат лежит на дне, затем насосы вытесняют воду до упора.
Ещё два неизвестных опыта: объём воды в начале и момент включения насосов.

Результат записан в rov_params.json вручную (tank_rate, heave_damping_lin).
Рис. 49 и т. 9 в подгонке НЕ участвуют: на них проверяется предсказание (v3_pid.py).
"""
import numpy as np
from scipy.optimize import differential_evolution

from common import OUT, plt, save_results
from rov import params, dynamics as dyn

p = params.load()
veh = dyn.Vehicle(p)
rho, g = p["rho"], p["g"]
Zw = veh.MA[2, 2]
d_quad = veh.d_quad[2] + sum(0.5 * rho * f["area"] * f["cd_plate"] for f in p["fins"] if f["normal"] == 2)
Vn = p["neutral_tank_volume"]
BOTTOM = 3.07   # показание на дне в начале рис. 48
DT = 0.02

data = np.loadtxt(OUT / "dunaev_fig48_digitized.csv", delimiter=",", skiprows=1)
data = data[(data[:, 0] >= 0) & (data[:, 0] <= 78)]


def sim(t, q, c, V0, t_on):
    z, w, V = BOTTOM, 0.0, V0
    out = np.empty(len(t))
    k, tt = 0, 0.0
    while k < len(t):
        Vdot = -2 * q if (tt >= t_on and V > 0) else 0.0
        V = max(V + Vdot * DT, 0.0)
        m = p["mass_dry"] + rho * V
        F = rho * g * (V - Vn) - d_quad * abs(w) * w - c * w
        w += F / (m + Zw) * DT
        z += w * DT
        if z >= BOTTOM and w > 0:
            z, w = BOTTOM, 0.0
        tt += DT
        while k < len(t) and t[k] <= tt:
            out[k] = z
            k += 1
    return out


def cost(x):
    return float(np.mean((sim(data[:, 0], *x) - data[:, 1]) ** 2))


bounds = [(0.2e-6, 8e-6), (0.0, 100.0), (Vn, 140e-6), (0.0, 40.0)]
r = differential_evolution(cost, bounds, seed=5, popsize=20, maxiter=150, tol=1e-10, polish=True)
q, c, V0, t_on = r.x
rms = float(np.sqrt(r.fun))

# шум датчика глубины по рис. 49: разброс вокруг скользящего среднего 5 с
f49 = np.loadtxt(OUT / "dunaev_fig49_digitized.csv", delimiter=",", skiprows=1)
win = int(5 / np.median(np.diff(f49[:, 0])))
smooth = np.convolve(f49[:, 1], np.ones(win) / win, mode="same")
noise = float(np.std((f49[:, 1] - smooth)[win:-win]))

res = {"tank_rate_m3_s": q, "heave_damping_lin": c, "V0_m3": V0, "pumps_on_s": t_on, "rms_m": rms,
       "neutral_tank_volume_m3": Vn,
       "depth_noise_sigma_fig49_m": noise,
       "note": "q и c зависят от нейтральности: при 40 мл получилось бы 0,83 мл/с и 4,3; при 100 мл 2,14 мл/с и 15,0. "
               "Шум оцифровки (1 пиксель) около 4 мм, он входит в оценку шума датчика"}
save_results("calibration_fig48", res)
print(res)

fig, ax = plt.subplots(figsize=(6.5, 4))
ax.plot(data[:, 0], data[:, 1], "b", label="рис. 48 Дунаева (оцифровка)")
ax.plot(data[:, 0], sim(data[:, 0], *r.x), "r--", label=f"модель: q = {q*1e6:.2f} мл/с, c = {c:.1f} Н·с/м")
ax.invert_yaxis()
ax.set(title=f"Калибровка по рис. 48: RMS {rms*1000:.0f} мм", xlabel="t, с", ylabel="глубина, м")
ax.legend(fontsize=8)
fig.tight_layout()
fig.savefig(OUT / "calibration_fig48.png")
