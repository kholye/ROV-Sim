"""V7: ил от движителей (rov/silt.py, physics-sources.md, разд. 29).

(а) струя над дном: наибольшая скорость у дна по модели (Albertson 1950) против независимой формулы
    винтовой струи Blaauw, van de Kaa 1978: U_b = 0,30·U0·D/h (допуск 5 %)
(б) порог размыва: на какой высоте движителя над дном полный ход начинает поднимать ил
(в) баланс масс: размыто = во взвеси + осело + убрано (до 1e-12 относительно)
(г) оседание: клуб высоко над дном без струй и течения опускается ровно со скоростью w_s
(д) оптика: точный интеграл концентрации вдоль луча (erf) против численной квадратуры
(е) сценарий для показа: аппарат у дна полным ходом 10 с, затем 50 с стоит; течение 0,1 м/с
(ж) порт Godot = эталон (относительно < 1e-6): тот же сценарий (с дифферентом и задним ходом, течение без порывов) в
    godot/tests/physics_tests.gd -> docs/verification/v2_godot_silt.csv
"""
import numpy as np

from common import OUT, plt, save_results, verdict
from rov import params, dynamics as dyn
from rov.environment import Current
from rov.silt import SiltPlume, Puff
from rov.light import silt_line

p = params.load()
res = {}
fig, ax = plt.subplots(1, 3, figsize=(14, 4))

# (а) наибольшая скорость у дна под горизонтальной струёй на высоте h
pl = SiltPlume(p)
U0, D = 3.0, p["thruster_duct_d"]
hs = np.linspace(0.05, 1.0, 40)
xs = np.geomspace(0.01, 50.0, 20000)
ub = np.array([max(pl.bed_speed(xa, h, U0, D) for xa in xs) for h in hs])
ref = 0.30 * U0 * D / hs
err = np.max(np.abs(ub / ref - 1))
res["a_max_rel_err"] = float(err)
res["a_pass"] = bool(err < 0.05)
ax[0].plot(hs, ub, label="модель (Albertson)")
ax[0].plot(hs, ref, "--", label="0,30·U0·D/h (Blaauw, van de Kaa)")
ax[0].set_xlabel("высота оси струи над дном h, м")
ax[0].set_ylabel("наибольшая скорость у дна, м/с")
ax[0].set_title(f"(а) U0 = {U0} м/с, D = {D * 1000:.0f} мм: {verdict(res['a_pass'])}")
ax[0].legend()

# (б) порог размыва при полном ходе
x = dyn.initial_state(7.0)
jet = pl.jets(x, (1.0, 1.0))[0]
U0f = jet[2]
res["b_U0_full"] = float(U0f)
h_axis = np.linspace(0.02, 0.8, 79)
mdot = []
for h in h_axis:
    bed = jet[0][2] + h
    mdot.append(pl.erosion(jet, bed)[0])
mdot = np.array(mdot)
h_thr = float(h_axis[np.nonzero(mdot > 0)[0][-1]]) if np.any(mdot > 0) else 0.0
res["b_h_threshold"] = h_thr
res["b_mdot_at_0.1m_g_s"] = float(np.interp(0.1, h_axis, mdot) * 1000)
res["b_mdot_at_0.2m_g_s"] = float(np.interp(0.2, h_axis, mdot) * 1000)
ax[1].semilogy(h_axis, np.maximum(mdot * 1000, 1e-6))
ax[1].set_xlabel("высота оси движителя над дном, м")
ax[1].set_ylabel("размыв одной струёй, г/с")
ax[1].set_title(f"(б) полный ход, U0 = {U0f:.2f} м/с: ил до h ≈ {h_thr:.2f} м")

# (в) + (е) сценарий: аппарат у дна, ось движителей в 0,15 м над илом
seabed = 8.0
x = dyn.initial_state(seabed - 0.15 - p["thruster_pos"][2], psi=0.3)
cur = Current(p["current_wreck_speed"], np.radians(p["current_wreck_dir_deg"]), p["current_wreck_T"],
              p["current_wreck_std"] * np.sqrt(2 / p["current_wreck_T"]), np.random.default_rng(3))
pl = SiltPlume(p)
dt = 0.1
tt, susp, bmax, npf = [], [], [], []
bal = 0.0
for i in range(600):
    thr = (1.0, 1.0) if i < 100 else (0.0, 0.0)
    cur.step(dt)
    pl.step(dt, x, thr, (seabed, seabed), cur, seabed)
    tot = pl.suspended() + pl.deposited + pl.removed
    if pl.eroded > 0:
        bal = max(bal, abs(tot - pl.eroded) / pl.eroded)
    tt.append((i + 1) * dt)
    susp.append(pl.suspended() * 1000)
    bmax.append(max([f.peak_c() * 2 * 500.0 for f in pl.puffs], default=0.0))
    npf.append(len(pl.puffs))
res["c_balance_rel"] = float(bal)
res["c_pass"] = bool(bal < 1e-12)
res["e_eroded_g"] = float(pl.eroded * 1000)
res["e_suspended_end_g"] = float(susp[-1])
res["e_peak_b_10s"] = float(bmax[99])
res["e_peak_b_60s"] = float(bmax[-1])
res["e_puffs_end"] = int(npf[-1])
f0 = max(pl.puffs, key=lambda f: f.m) if pl.puffs else None
if f0:
    res["e_main_puff_60s"] = {"m_g": f0.m * 1000, "sigma_h": f0.sh, "sigma_z": f0.sz,
                              "drift_m": float(np.linalg.norm(f0.pos[:2] - x[:2]))}
ax[2].plot(tt, susp, label="во взвеси, г")
ax[2].plot(tt, bmax, label="пиковое рассеяние, 1/м")
ax[2].axvline(10, color="k", lw=0.5)
ax[2].set_xlabel("время, с (полный ход до 10 с)")
ax[2].set_title(f"(в, е) баланс масс {bal:.1e}: {verdict(res['c_pass'])}")
ax[2].legend()

# (г) оседание
pl = SiltPlume(p)
pl.puffs.append(Puff([0, 0, 3.0], 1e-3, 0.3, 0.3, 8.0))
for i in range(1000):
    pl.step(0.1, dyn.initial_state(1.0), (0, 0), (np.nan, np.nan), None, 0.0)
v = (pl.puffs[0].pos[2] - 3.0) / 100.0
res["d_ws_model"] = float(v)
res["d_pass"] = bool(abs(v / p["silt_ws"] - 1) < 1e-9)

# (д) оптика
f = Puff([2.0, 0.3, 7.6], 2e-3, 0.4, 0.25, 8.0)
cam = np.array([0.0, 0.0, 7.0])                   # NED; в оптике ось «вверх» (0, 0, 1) после смены знака z
rng = np.random.default_rng(1)
dirs = rng.normal(size=(50, 3))
dirs[:, 0] = np.abs(dirs[:, 0]) + 1.0
dirs /= np.linalg.norm(dirs, axis=1)[:, None]
Ds = rng.uniform(0.5, 6.0, 50)
exact = silt_line(cam * [1, 1, -1], dirs * [1, 1, -1], Ds, f.pos * [1, 1, -1], f.m, f.sh, f.sz, -f.bed, np.array([0.0, 0.0, 1.0]))[0]
num = []
for d, Dd in zip(dirs, Ds):
    t = np.linspace(0, Dd, 20001)
    P = cam + d * t[:, None]
    c = 0.0
    for z0 in (f.pos[2], 2 * f.bed - f.pos[2]):
        q = (P - np.array([f.pos[0], f.pos[1], z0])) / np.array([f.sh, f.sh, f.sz])
        c = c + f.m / ((2 * np.pi) ** 1.5 * f.sh ** 2 * f.sz) * np.exp(-0.5 * np.sum(q * q, axis=1))
    num.append(np.trapezoid(c, t))
num = np.array(num)
oerr = float(np.max(np.abs(exact - num)) / np.max(num))
res["f_line_integral_rel_err"] = oerr
res["f_pass"] = bool(oerr < 1e-6)

# (ж) Godot против эталона
pl = SiltPlume(p)
cur0 = Current(p["current_wreck_speed"], np.radians(p["current_wreck_dir_deg"]))
x = dyn.initial_state(8.0 - 0.15 - p["thruster_pos"][2], psi=0.3)
x[4] = np.radians(4.0)
for i in range(600):
    thr = (1.0, 0.8) if i < 100 else ((-0.6, -0.6) if i < 150 else (0.0, 0.0))
    pl.step(0.1, x, thr, (8.0, 8.0), cur0, 8.0)
gpath = OUT / "v2_godot_silt.csv"
if gpath.exists():
    rows = [list(map(float, r.split(","))) for r in gpath.read_text(encoding="utf-8").split()]
    tot = np.array(rows[0])
    gp = np.array(rows[1:])
    py = np.array([[*f.pos, f.m, f.sh, f.sz] for f in pl.puffs])
    if gp.shape == py.shape:
        rel = float(np.max(np.abs(gp - py) / (np.abs(py) + 1e-12)))
    else:
        rel = float("inf")
    rel_tot = float(np.max(np.abs(tot - [pl.eroded, pl.deposited, pl.removed, pl.suspended()])
                           / max(pl.eroded, 1e-30)))
    res["g_godot_vs_python_puffs_rel"] = rel
    res["g_godot_vs_python_mass_rel"] = rel_tot
    res["g_puffs"] = int(len(pl.puffs))
    res["g_pass"] = bool(rel < 1e-6 and rel_tot < 1e-6)   # округление за 600 шагов и слияния
else:
    res["g_pass"] = False
    print("нет", gpath, "— сначала physics_tests.gd")

fig.tight_layout()
fig.savefig(OUT / "v7_silt.png")
save_results("v7_silt", res)
for k, v in res.items():
    print(k, v)
print("V7:", verdict(res["a_pass"] and res["c_pass"] and res["d_pass"] and res["f_pass"] and res["g_pass"]))
