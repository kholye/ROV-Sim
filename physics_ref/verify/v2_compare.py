"""V2: одинаковые входы в Python-эталон и в Godot (GDScript), 60 с.

Эталон: scipy solve_ivp (DOP853, rtol 1e-11), независимый интегратор с переменным шагом.
Контроль: Python RK4 с тем же шагом 0,005 с, что и Godot (отделяет ошибку интегратора от ошибки порта).
Критерий: глубина < 1 мм, углы < 0,01°.

Перед запуском: Godot_console --headless --path godot --script res://tests/physics_tests.gd -- docs/verification/v2_godot.csv
"""
import numpy as np
from scipy.integrate import solve_ivp

from common import OUT, plt, save_results, verdict
from rov import params, dynamics as dyn

p = params.load()
veh = dyn.Vehicle(p)
vc = (0.1, 0.05, 0.0)


def schedule(seg):
    if seg < 100: thr = (0.6, 0.6)
    elif seg < 200: thr = (0.8, -0.2)
    elif seg < 300: thr = (0.0, 0.0)
    elif seg < 450: thr = (-0.5, -0.3)
    else: thr = (0.3, 0.7)
    if seg < 150: tank = (1, 0)
    elif seg < 300: tank = (0, -1)
    elif seg < 450: tank = (-1, -1)
    else: tank = (1, 1)
    return thr, tank


x0 = dyn.initial_state(1.0, 0.3, 50e-6, 20e-6)

# эталон
ref = [x0.copy()]
x = x0.copy()
for seg in range(600):
    thr, tank = schedule(seg)
    sol = solve_ivp(lambda t, y: veh.deriv(y, thr, tank, vc)[0], (0, 0.1), x, method="DOP853",
                    rtol=1e-11, atol=1e-13)
    x = dyn.clamp_tanks(sol.y[:, -1].copy(), p["tank_capacity"])
    ref.append(x.copy())
ref = np.array(ref)

# Python RK4
rk = [x0.copy()]
x = x0.copy()
for seg in range(600):
    thr, tank = schedule(seg)
    for _ in range(20):
        x, _ = dyn.rk4_step(veh, x, 0.005, thr, tank, vc)
    rk.append(x.copy())
rk = np.array(rk)

gd = np.loadtxt(OUT / "v2_godot.csv", delimiter=",", skiprows=1)
t = gd[:, 0]
gd = gd[:, 1:]


def wrap(a):
    return (a + np.pi) % (2 * np.pi) - np.pi


def errs(a, b):
    return {"depth_mm": float(np.abs(a[:, 2] - b[:, 2]).max() * 1000),
            "position_mm": float(np.linalg.norm(a[:, :3] - b[:, :3], axis=1).max() * 1000),
            "angle_deg": float(np.degrees(np.abs(wrap(a[:, 3:6] - b[:, 3:6])).max())),
            "tank_ml": float(np.abs(a[:, 12:14] - b[:, 12:14]).max() * 1e6)}


res = {"godot_vs_reference": errs(gd, ref), "godot_vs_python_rk4": errs(gd, rk),
       "python_rk4_vs_reference": errs(rk, ref),
       "final_state_reference": {"depth_m": ref[-1, 2], "psi_deg": float(np.degrees(ref[-1, 5])),
                                 "theta_deg": float(np.degrees(ref[-1, 4]))}}
# производные в состояниях вне V2 (в том числе после сброса груза): те же, что DERIV_STATES в physics_tests.gd
DERIV_STATES = [
    ([1, 2, 1.5, 0.2, -0.15, 0.7, 0.4, -0.1, 0.05, 0.3, -0.2, 0.25, 60e-6, 10e-6], (0.7, -0.4), (0.1, -0.05, 0.02), False),
    ([0, 0, 2.0, -0.1, 0.2, -1.0, -0.2, 0.15, -0.1, -0.1, 0.3, -0.2, 20e-6, 50e-6], (-0.3, 0.9), (0, 0, 0), True),
    ([0, 0, 0.5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 35e-6, 35e-6], (0, 0), (0, 0, 0), True),
    # с внешней силой кабеля (версия 1.2): сила в NED и точка на кормовом гермовводе
    ([3, -1, 6.0, 0.1, -0.2, 2.0, 0.3, 0.05, -0.02, 0.1, -0.1, 0.2, 40e-6, 30e-6], (0.5, 0.2), (0.08, 0.03, 0), False,
     ((-2.0, 0.7, -0.4), (-0.35, 0.0, -0.028))),
]
gd_d = np.loadtxt(OUT / "v2_godot_deriv.csv", delimiter=",", ndmin=2)
dmax = 0.0
for k, (xs, thr, vcs, dropped, *ext) in enumerate(DERIV_STATES):
    xd, nud = veh.deriv(np.array(xs, dtype=float), thr, (0, 0), vcs, dropped, ext[0] if ext else None)
    py = np.concatenate([xd, nud])
    dmax = max(dmax, float(np.abs(py - gd_d[k]).max() / (np.abs(py).max() + 1e-12)))
res["deriv_rel_err_max"] = dmax

e = res["godot_vs_reference"]
res["ok"] = bool(e["depth_mm"] < 1.0 and e["angle_deg"] < 0.01 and dmax < 1e-9)

fig, ax = plt.subplots(2, 2, figsize=(12, 7))
ax[0, 0].plot(ref[:, 1], ref[:, 0], label="эталон SciPy")
ax[0, 0].plot(gd[:, 1], gd[:, 0], "--", label="Godot")
ax[0, 0].set(title="траектория в плане (x север, y восток)", xlabel="y, м", ylabel="x, м")
ax[0, 0].legend(fontsize=8)
ax[0, 1].plot(t, ref[:, 2], label="глубина эталон")
ax[0, 1].plot(t, gd[:, 2], "--", label="глубина Godot")
ax[0, 1].invert_yaxis()
ax[0, 1].set(title="глубина", xlabel="t, с", ylabel="z, м")
ax[0, 1].legend(fontsize=8)
ax[1, 0].semilogy(t, np.abs(gd[:, 2] - ref[:, 2]) * 1000 + 1e-12, label="|Δz| Godot − эталон")
ax[1, 0].semilogy(t, np.abs(gd[:, 2] - rk[:, 2]) * 1000 + 1e-12, label="|Δz| Godot − Python RK4")
ax[1, 0].axhline(1.0, color="r", ls=":", label="допуск 1 мм")
ax[1, 0].set(title="расхождение глубины", xlabel="t, с", ylabel="мм")
ax[1, 0].legend(fontsize=8)
for k, nm in zip(range(3, 6), ("φ", "θ", "ψ")):
    ax[1, 1].semilogy(t, np.degrees(np.abs(wrap(gd[:, k] - ref[:, k]))) + 1e-14, label=f"|Δ{nm}|")
ax[1, 1].axhline(0.01, color="r", ls=":", label="допуск 0,01°")
ax[1, 1].set(title="расхождение углов Godot − эталон", xlabel="t, с", ylabel="°")
ax[1, 1].legend(fontsize=8)
fig.tight_layout()
fig.savefig(OUT / "v2_compare.png")
save_results("v2", res)
for k, v in res.items():
    print(k, v)
print("V2:", verdict(res["ok"]))
