"""V1: полная модель 6 ст. св. против формул.

(а) падение с полными цистернами и всплытие с пустыми: w(t) = w_t·tanh(t/tau)
(б) ход вперёд на полной тяге, поворот на месте: предельные скорости
(в) равновесие: нейтральный аппарат 10 минут, уход глубины < 1 мм
(г) дифферент от разницы цистерн: tan(theta) = -x_g / z_g
(д) присоединённые массы: полосовая теория против эллипсоида Лэмба (справочно)
(е) устойчивость прямого хода без плоскостей и с плоскостями (собственные числа)
(ж) полная модель (плоскости + линейное затухание по вертикали): падение с полными цистернами,
    d·w² + c·w = ΔF, w_t = (−c + √(c² + 4dΔF)) / 2d

(а)-(г) считаются для «голого» корпуса (без плоскостей и без линейного затухания по вертикали),
чтобы каждая формула проверяла один член уравнения.
"""
import numpy as np

from common import OUT, plt, save_results, verdict
from rov import params, dynamics as dyn

p = params.load(fins=[], heave_damping_lin=0.0)
veh = dyn.Vehicle(p)
p_fins = params.load()
rho, g = p["rho"], p["g"]
res = {}


def simulate(x, t_end, dt, thr=(0, 0), tank=(0, 0), dropped=False):
    n = int(round(t_end / dt))
    hist = np.zeros((n + 1, 15))
    hist[0, 0], hist[0, 1:] = 0.0, x
    for i in range(n):
        x, _ = dyn.rk4_step(veh, x, dt, thr, tank, dropped=dropped)
        hist[i + 1, 0], hist[i + 1, 1:] = (i + 1) * dt, x
    return hist


fig, ax = plt.subplots(2, 3, figsize=(13, 7))

# (а) вертикаль
for k, (V, label) in enumerate(((70e-6, "падение, цистерны полные"), (0.0, "всплытие, цистерны пустые"))):
    x0 = dyn.initial_state(1.0 if V > 0 else 30.0, V1=V, V2=V)
    h = simulate(x0, 120.0, 0.01)
    m = p["mass_dry"] + rho * 2 * V
    dF = m * g - rho * g * veh.displaced_volume(False)
    wt = np.sign(dF) * np.sqrt(abs(dF) / veh.d_quad[2])
    tau = (m + veh.MA[2, 2]) / np.sqrt(abs(dF) * veh.d_quad[2])
    w_an = wt * np.tanh(h[:, 0] / tau)
    w_sim = h[:, 9]
    err = np.abs(w_sim - w_an).max() / abs(wt)
    key = "sink" if V > 0 else "rise"
    res[key] = {"w_terminal_formula": wt, "w_terminal_sim": w_sim[-1], "tau_s": tau,
                "max_rel_error_curve": err, "ok": bool(err < 0.01)}
    ax[0, 0].plot(h[:, 0], w_sim, label=f"{label}: модель")
    ax[0, 0].plot(h[:, 0], w_an, "k--", lw=0.8)
ax[0, 0].set(title="(а) вертикальная скорость; пунктир: w_t·tanh(t/τ)", xlabel="t, с", ylabel="w, м/с (вниз +)")
ax[0, 0].legend(fontsize=7)

# сброс балласта: всплытие
x0 = dyn.initial_state(30.0)
h = simulate(x0, 60.0, 0.01, dropped=True)
m = p["mass_dry"] - p["ballast_drop_mass"] + rho * 70e-6
dF = m * g - rho * g * veh.displaced_volume(True)
wt = -np.sqrt(-dF / veh.d_quad[2])
err = abs(h[-1, 9] - wt) / abs(wt)
res["ballast_drop"] = {"net_up_force_N": -dF, "w_terminal_formula": wt, "w_terminal_sim": h[-1, 9],
                       "rel_error": err, "ok": bool(err < 0.01)}

# (б) ход и поворот
# Ход вперёд: формула верна, только пока корпус устойчив (см. (е)). Малая тяга: u_t = 0,3 м/с.
u_low = 0.3
s_low = np.sqrt(veh.d_quad[0] * u_low ** 2 / (2 * p["thrust_max"]))
h = simulate(dyn.initial_state(1.0), 120.0, 0.01, thr=(s_low, s_low))
err = abs(h[-1, 7] - u_low) / u_low
res["surge_low"] = {"thrust_cmd": s_low, "u_terminal_formula": u_low, "u_terminal_sim": h[-1, 7],
                    "theta_end_deg": float(np.degrees(h[-1, 5])), "rel_error": err, "ok": bool(err < 0.01)}
ax[0, 1].plot(h[:, 0], h[:, 7], label=f"u, тяга {100*s_low:.0f} % (устойчиво)")
ax[0, 1].axhline(u_low, color="k", ls="--", lw=0.8)
h = simulate(dyn.initial_state(1.0), 60.0, 0.01, thr=(1.0, 1.0))
ut = np.sqrt(2 * p["thrust_max"] / veh.d_quad[0])
res["surge_full"] = {"u_terminal_formula": ut, "u_sim_at_60s": h[-1, 7], "theta_max_deg": float(np.degrees(np.abs(h[:, 5]).max())),
                     "max_abs_sway_heave": float(np.abs(h[:, 8:10]).max()),
                     "note": "на полной тяге корпус без плоскостей теряет устойчивость по дифференту; это не проверка формулы, а находка (см. stability)"}
ax[0, 1].plot(h[:, 0], h[:, 7], label="u, тяга 100 % (неустойчиво)")
ax[0, 1].axhline(ut, color="k", ls=":", lw=0.8, label="√(2T/d_u) при 100 %")
ax[0, 1].set(title="(б) ход вперёд", xlabel="t, с", ylabel="u, м/с")
ax[0, 1].legend(fontsize=7)

h = simulate(dyn.initial_state(1.0), 60.0, 0.01, thr=(1.0, -1.0))
y_t = p["thruster_pos"][1]
rt = np.sqrt(2 * y_t * p["thrust_max"] / veh.d_quad[5])
err = abs(h[-1, 12] - rt) / rt
res["yaw"] = {"r_terminal_formula": rt, "r_terminal_sim": h[-1, 12], "rel_error": err, "ok": bool(err < 0.01)}
ax[0, 2].plot(h[:, 0], np.degrees(h[:, 12]), label="r модель")
ax[0, 2].axhline(np.degrees(rt), color="k", ls="--", lw=0.8, label="√(2·y·T/d_r)")
ax[0, 2].set(title="(б) разворот на месте (+100 / −100)", xlabel="t, с", ylabel="r, °/с")
ax[0, 2].legend(fontsize=7)

# (в) равновесие 10 минут
h = simulate(dyn.initial_state(1.5), 600.0, 0.05)
drift = np.abs(h[:, 3] - 1.5).max()
res["equilibrium"] = {"max_depth_drift_m": drift, "ok": bool(drift < 1e-3),
                      "max_speed": float(np.abs(h[:, 7:13]).max())}
ax[1, 0].plot(h[:, 0], (h[:, 3] - 1.5) * 1000)
ax[1, 0].set(title=f"(в) нейтральный в покое: уход {drift*1000:.2e} мм", xlabel="t, с", ylabel="z − 1,5, мм")

# (г) дифферент
h = simulate(dyn.initial_state(1.5, V1=70e-6, V2=0.0), 900.0, 0.02)
m, rg, _ = veh.mass_props(70e-6, 0.0, False)
rb = veh.buoyancy_center(False)
# W = B (в цистернах вместе 70 мл): момент (z_g − z_b) W sinθ + (x_g − x_b) W cosθ = 0
th_an = np.arctan2(-(rg[0] - rb[0]), rg[2] - rb[2])
th_end = np.mean(h[-3000:, 5])
err = abs(th_end - th_an) / abs(th_an)
res["trim"] = {"theta_formula_deg": np.degrees(th_an), "theta_sim_last60s_deg": np.degrees(th_end),
               "theta_amplitude_last60s_deg": float(np.degrees(np.ptp(h[-3000:, 5]) / 2)),
               "rel_error": err, "ok": bool(err < 0.01)}
ax[1, 1].plot(h[:, 0], np.degrees(h[:, 5]), label="θ модель")
ax[1, 1].axhline(np.degrees(th_an), color="k", ls="--", lw=0.8, label="−atan((x_g − x_b)/(z_g − z_b))")
ax[1, 1].set(title="(г) носовая полная, кормовая пустая", xlabel="t, с", ylabel="θ, °")
ax[1, 1].legend(fontsize=7)

# (д) присоединённые массы
L, D = p["hull_length"], p["hull_diameter"]
k1, k2, kr = dyn.lamb_k(L, D)
a, b = L / 2, D / 2
V_sph = 4 / 3 * np.pi * a * b * b
I_sph = rho * V_sph * (a * a + b * b) / 5
lamb = [k1 * rho * V_sph, k2 * rho * V_sph, kr * I_sph]
strip = [veh.MA[0, 0], veh.MA[2, 2], veh.MA[4, 4]]
res["added_mass"] = {"names": ["X_u'", "Z_w'", "M_q'"], "model": strip, "lamb_spheroid": lamb,
                     "ratio_model_to_spheroid": [s / l for s, l in zip(strip, lamb)],
                     "note": "эллипсоид того же L/D имеет объём 2/3 цилиндра; справочное сравнение, не критерий"}
lbl = ["X_u̇, кг", "Z_ẇ, кг", "M_q̇, кг·м²"]
xx = np.arange(3)
ax[1, 2].bar(xx - 0.2, strip, 0.4, label="модель (полосы; X по Лэмбу)")
ax[1, 2].bar(xx + 0.2, lamb, 0.4, label="эллипсоид Лэмба")
ax[1, 2].set_xticks(xx, lbl)
ax[1, 2].set_yscale("log")
ax[1, 2].set(title="(д) присоединённые массы (справочно)")
ax[1, 2].legend(fontsize=7)

fig.tight_layout()
fig.savefig(OUT / "v1_analytic.png")

# (е) устойчивость прямого хода: собственные числа линеаризованной модели в точке u0, theta = 0
def jac(v, x0, thr):
    n = 12
    J = np.zeros((n, n))
    f0 = v.deriv(x0, thr, (0, 0))[0][:n]
    for j in range(n):
        dx = np.zeros(14)
        dx[j] = 1e-6
        J[:, j] = (v.deriv(x0 + dx, thr, (0, 0))[0][:n] - f0) / 1e-6
    return J


speeds = np.linspace(0.02, 2.0, 60)
m0, rg0, _ = veh.mass_props(35e-6, 35e-6, False)
munk = veh.MA[2, 2] - veh.MA[0, 0]
u_crit_formula = np.sqrt(m0 * g * (rg0[2] - veh.buoyancy_center(False)[2]) / munk)
res["stability"] = {"u_crit_pitch_formula_bare": u_crit_formula,
                    "formula": "W·(z_g − z_b) = (Z_ẇ − X_u̇)·u²  (момент Мунка против восстанавливающего, без плоскостей)"}
fig2, a2 = plt.subplots(figsize=(6.5, 3.8))
for label, pp, ls in (("без плоскостей", p, "--"), ("с плоскостями (оценка по фото)", p_fins, "-")):
    v = dyn.Vehicle(pp)
    lam_pitch, lam_yaw = [], []
    for u0 in speeds:
        s0 = np.sqrt(v.d_quad[0] * u0 ** 2 / (2 * pp["thrust_max"]))
        x0 = dyn.initial_state(1.5)
        x0[6] = u0
        J = jac(v, x0, (s0, s0))
        vert = [2, 4, 8, 10]       # z, theta, w, q
        horz = [1, 5, 7, 11]       # y, psi, v, r
        lam_pitch.append(np.linalg.eigvals(J[np.ix_(vert, vert)]).real.max())
        lam_yaw.append(np.linalg.eigvals(J[np.ix_(horz, horz)]).real.max())
    lam_pitch, lam_yaw = np.array(lam_pitch), np.array(lam_yaw)
    i03 = np.argmin(abs(speeds - 0.3))
    res["stability"][label] = {
        "u_crit_pitch_eigen": float(speeds[np.argmax(lam_pitch > 1e-3)]) if np.any(lam_pitch > 1e-3) else None,
        "yaw_unstable_from_speed": float(speeds[np.argmax(lam_yaw > 1e-3)]) if np.any(lam_yaw > 1e-3) else None,
        "yaw_growth_at_0_3_m_s": float(lam_yaw[i03]),
        "yaw_e_fold_time_at_0_3_m_s": float(1 / lam_yaw[i03]) if lam_yaw[i03] > 0 else None}
    a2.plot(speeds, lam_pitch, "C0" + ls, label=f"вертикальная плоскость, {label}")
    a2.plot(speeds, lam_yaw, "C1" + ls, label=f"курс, {label}")
a2.axvline(u_crit_formula, color="k", ls=":", lw=0.8, label=f"формула без плоскостей: {u_crit_formula:.2f} м/с")
a2.axhline(0, color="gray", lw=0.6)
a2.set(title="(е) устойчивость прямого хода", xlabel="u₀, м/с", ylabel="max Re λ, 1/с (> 0: неустойчиво)")
a2.legend(fontsize=6.5)
fig2.tight_layout()
fig2.savefig(OUT / "v1_stability.png")

# (ж) плоскости: падение с полными цистернами
veh_f = dyn.Vehicle(p_fins)
x = dyn.initial_state(1.0, V1=70e-6, V2=70e-6)
for _ in range(6000):
    x, _ = dyn.rk4_step(veh_f, x, 0.01, (0, 0), (0, 0))
d_plate = sum(0.5 * rho * f["area"] * f["cd_plate"] for f in p_fins["fins"] if f["normal"] == 2)
dF = rho * g * 70e-6
dq = veh.d_quad[2] + d_plate
c = p_fins["heave_damping_lin"]
wt_f = (-c + np.sqrt(c * c + 4 * dq * dF)) / (2 * dq)
w_end = dyn.rot_nb(*x[3:6]) @ x[6:9]
err = abs(w_end[2] - wt_f) / wt_f
res["fins_sink"] = {"w_terminal_formula": wt_f, "w_terminal_sim": float(w_end[2]), "theta_deg": float(np.degrees(x[4])),
                    "rel_error": err, "ok": bool(err < 0.01),
                    "heave_damping_lin": c, "note": "носовые плоскости тормозят нос: аппарат падает с небольшим дифферентом"}

res["all_ok"] = all(v["ok"] for v in res.values() if isinstance(v, dict) and "ok" in v)
save_results("v1", res)
for k, v in res.items():
    print(k, v)
print("V1:", verdict(res["all_ok"]))
