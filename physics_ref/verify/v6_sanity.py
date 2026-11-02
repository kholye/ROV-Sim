"""V6: здравый смысл.

(а) нет бесплатной энергии: без тяги механическая энергия (кинетическая с присоединёнными массами
    + потенциал веса и плавучести) не растёт, а её убыль равна работе сопротивления
(б) батарея: энергия только убывает и равна интегралу потребляемой мощности
(в) нейтральный аппарат в покое остаётся в покое (10 минут)
"""
import numpy as np

from common import OUT, plt, save_results, verdict
from rov import params, dynamics as dyn
from rov.environment import Battery

p = params.load()
veh = dyn.Vehicle(p)
res = {}
fig, ax = plt.subplots(1, 3, figsize=(14, 4))

# (а)
dt, T = 0.01, 120.0
x = dyn.initial_state(2.0, V1=50e-6, V2=20e-6)
x[6:12] = [0.3, 0.1, -0.05, 0.4, 0.2, 0.3]
x[3] = 0.2
n = int(T / dt)
E = np.zeros(n + 1)
Pd = np.zeros(n + 1)
tt = np.arange(n + 1) * dt


def p_diss(x):
    nu = x[6:12]
    # линейное затухание + сопротивление по силуэтам + плоскости (drag и fin_forces только гасят движение)
    return float(nu @ (veh.d_lin * nu) - nu @ veh.drag(nu) - nu @ veh.fin_forces(nu))


E[0], Pd[0] = veh.energy(x), p_diss(x)
for i in range(n):
    x, _ = dyn.rk4_step(veh, x, dt, (0, 0), (0, 0))
    E[i + 1], Pd[i + 1] = veh.energy(x), p_diss(x)
W_diss = np.concatenate([[0], np.cumsum(0.5 * (Pd[1:] + Pd[:-1]) * dt)])
balance = (E[0] - E) - W_diss
rise = np.diff(E).max()
res["mechanical_energy"] = {"dE_total_J": E[-1] - E[0],
                            "max_step_increase_J": rise, "max_balance_error_J": float(np.abs(balance).max()),
                            "ok": bool(rise <= 1e-9 and np.abs(balance).max() < 1e-4 * abs(E[0] - E[-1]))}
ax[0].plot(tt, E - E[0], label="E(t) − E(0)")
ax[0].plot(tt, -W_diss, "--", label="−∫ νᵀDν dt")
ax[0].set(title="(а) энергия без тяги", xlabel="t, с", ylabel="Дж")
ax[0].legend(fontsize=8)

# (б) батарея: смешанный режим 30 минут
b = Battery(p)
rng = np.random.default_rng(2)
dtb = 0.5
Es, Ps, Vs = [b.E], [], []
for i in range(3600):
    thr = rng.uniform(-1, 1, 2) if (i // 120) % 2 else (0, 0)
    tank = (rng.integers(-1, 2), rng.integers(-1, 2))
    P = b.step(dtb, thr, tank, lamp=1.0)
    Ps.append(P)
    Vs.append(b.voltage(P))
    Es.append(b.E)
Es = np.array(Es)
res["battery"] = {"monotonic": bool(np.all(np.diff(Es) <= 0)),
                  "E_used_J": b.used, "integral_P_J": float(np.sum(Ps) * dtb),
                  "soc_end": b.soc(),
                  "hotel_plus_lamp_runtime_h": p["battery_energy"] / (p["power_hotel"] + p["power_lamp"]),
                  "note": "ёмкость 43,2 Вт·ч подобрана под «до 2 часов» при средней нагрузке ≈21,6 Вт (оценка)"}
res["battery"]["ok"] = bool(res["battery"]["monotonic"] and abs(res["battery"]["E_used_J"] - res["battery"]["integral_P_J"]) < 1e-6 * b.used)
ax[1].plot(np.arange(len(Es)) * dtb / 60, Es / 3600, label="энергия, Вт·ч")
ax2 = ax[1].twinx()
ax2.plot(np.arange(len(Vs)) * dtb / 60, Vs, "C1", lw=0.5)
ax2.set_ylabel("напряжение под нагрузкой, В", color="C1")
ax[1].set(title="(б) батарея, 30 мин смешанной работы", xlabel="t, мин", ylabel="Вт·ч")

# (в) покой
x = dyn.initial_state(1.5)
mx = 0.0
for i in range(12000):
    x, _ = dyn.rk4_step(veh, x, 0.05, (0, 0), (0, 0))
    mx = max(mx, float(np.abs(x[6:12]).max()))
res["rest"] = {"max_speed_10min": mx, "depth_change_m": float(x[2] - 1.5), "ok": bool(mx < 1e-9)}
ax[2].bar(["max |ν| за 10 мин"], [max(mx, 1e-18)])
ax[2].set_yscale("log")
ax[2].set(title=f"(в) нейтральный в покое: {mx:.1e}")

fig.tight_layout()
fig.savefig(OUT / "v6_sanity.png")
res["all_ok"] = all(v["ok"] for v in res.values() if isinstance(v, dict))
save_results("v6", res)
for k, v in res.items():
    print(k, v)
print("V6:", verdict(res["all_ok"]))
