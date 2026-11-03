"""V8: кабель-трос (rov/tether.py, physics-sources.md, разд. 30).

(а) цепная линия: кабель 12 м между точками на одной высоте в 10 м, без течения — форма и натяжение на конце
    против точной формулы цепной линии (Ирвин 1981, гл. 1)
(б) течение: кабель 14 м от точки у поверхности к точке в 10 м по горизонтали и 8 м глубже, течение 0,3 м/с
    вдоль плоскости — форма и натяжение против независимого решения уравнений равновесия нити
    (dT/ds = −f·t, T dφ/ds = −f·n; стрельба SciPy)
(в) длина: сумма звеньев против заданной (нерастяжимость)
(г) подача: аппарат уходит от судна 0,3 м/с — кабель стравливается до предела 22 м и не длиннее
(д) порт Godot = эталон: 2 с с течением, подачей и касаниями дна (godot/tests/physics_tests.gd ->
    docs/verification/v2_godot_tether.csv); дальше сравнивать нельзя — чувствительность: сдвиг узла на 1e-9 м
    через 3-4 с даёт сантиметры (трение покоя/скольжения и включение звеньев — разрывы в самой модели), (е)
(ж) трение (зацеп): кабель перекинут через неподвижную трубу R = 0,1 м (угол охвата π), один конец закреплён, другой
    медленно тянут вниз; отношение натяжений при проскальзывании против формулы Эйлера e^(μθ) — измерение, без порога
"""
import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq, fsolve

from common import OUT, plt, save_results, verdict
from rov import params
from rov.tether import Tether

p = params.load()
res = {}
fig, ax = plt.subplots(1, 3, figsize=(15, 4.2))
DT = 1 / 120

# (а) цепная линия
Dspan, L = 10.0, 12.0
tt = Tether(p, [0, 0, 0], [Dspan, 0, 0], L)
for _ in range(int(60 / DT)):
    tt.step(DT, np.array([Dspan, 0, 0.0]))
w = tt.w_net
a = brentq(lambda a: 2 * a * np.sinh(Dspan / (2 * a)) - L, 0.1, 100)
xs = tt.X[:, 0]
z_ref = a * (np.cosh((xs - Dspan / 2) / a) - np.cosh(Dspan / (2 * a))) * -1
sag = float(np.max(z_ref))
err = float(np.max(np.abs(tt.X[:, 2] - z_ref)))
T_ref = w * a * np.cosh(Dspan / (2 * a))
T_got = float(np.linalg.norm(tt.tension_end))
res["a_sag_m"] = sag
res["a_shape_err_m"] = err
res["a_tension_ref_N"] = float(T_ref)
res["a_tension_got_N"] = T_got
res["a_pass"] = bool(err < 0.01 * sag and abs(T_got / T_ref - 1) < 0.02)
ax[0].plot(xs, -tt.X[:, 2], "o", ms=3, label="модель (узлы)")
xx = np.linspace(0, Dspan, 200)
ax[0].plot(xx, a * (np.cosh((xx - Dspan / 2) / a) - np.cosh(Dspan / (2 * a))), label="цепная линия")
ax[0].set_title(f"(а) провис {sag:.2f} м, ошибка {err * 1000:.1f} мм, T {T_got:.3f}/{T_ref:.3f} Н: {verdict(res['a_pass'])}",
                fontsize=8)
ax[0].set_xlabel("x, м")
ax[0].set_ylabel("высота, м")
ax[0].legend()

# (б) течение
U = 0.3
Ls, B = 14.0, np.array([10.0, 0.0, 8.0])
water = lambda X: np.array([U, 0.0, 0.0])
tt = Tether(p, [0, 0, 0], B, Ls)
for _ in range(int(120 / DT)):
    tt.step(DT, B, water)
kn, kt = tt.kn, tt.kt


def rhs(s, y):
    x, z, phi, T = y
    t = np.array([np.cos(phi), np.sin(phi)])
    n = np.array([-np.sin(phi), np.cos(phi)])
    u = np.array([U, 0.0])
    un, ut = u @ n, u @ t
    f = np.array([0.0, w]) + kn * abs(un) * un * n + kt * abs(ut) * ut * t
    return [t[0], t[1], -(f @ n) / T, -(f @ t)]


def shoot(q):
    sol = solve_ivp(rhs, (0, Ls), [0, 0, q[0], q[1]], rtol=1e-10, atol=1e-12)
    return [sol.y[0, -1] - B[0], sol.y[1, -1] - B[2]]


d0 = tt.X[1] - tt.X[0]
q = fsolve(shoot, [np.arctan2(d0[2], d0[0]), max(tt.tension_top, 0.1)], xtol=1e-12)
res["b_bvp_residual_m"] = float(np.max(np.abs(shoot(q))))
s_nodes = np.concatenate(([0.0], np.cumsum(tt.rest)))
sol = solve_ivp(rhs, (0, Ls), [0, 0, q[0], q[1]], rtol=1e-10, atol=1e-12, dense_output=True)
ref = sol.sol(s_nodes)
errb = float(np.max(np.hypot(tt.X[:, 0] - ref[0], tt.X[:, 2] - ref[1])))
Tb_ref = float(sol.sol(Ls)[3])
Tb_got = float(np.linalg.norm(tt.tension_end))
res["b_shape_err_m"] = errb
res["b_tension_ref_N"] = Tb_ref
res["b_tension_got_N"] = Tb_got
res["b_pass"] = bool(errb < 0.03 and abs(Tb_got / Tb_ref - 1) < 0.03 and res["b_bvp_residual_m"] < 1e-6)
ax[1].plot(tt.X[:, 0], -tt.X[:, 2], "o", ms=3, label="модель (узлы)")
ss = np.linspace(0, Ls, 300)
r2 = sol.sol(ss)
ax[1].plot(r2[0], -r2[1], label="уравнения нити (SciPy)")
ax[1].set_title(f"(б) течение {U} м/с: ошибка {errb * 100:.1f} см, T {Tb_got:.2f}/{Tb_ref:.2f} Н: "
                f"{verdict(res['b_pass'])}", fontsize=8)
ax[1].set_xlabel("x, м")
ax[1].set_ylabel("−глубина, м")
ax[1].legend()

# (в) длина
seg_len = np.sum(np.linalg.norm(np.diff(tt.X, axis=0), axis=1))
res["c_length_rel_err"] = float(abs(seg_len / Ls - 1))
res["c_pass"] = bool(res["c_length_rel_err"] < 1e-3)

# (г) подача
end = np.array([3.0, 0.0, 8.0])
tt = Tether(p, [0, 0, 0], end, 11.0)
tl, ll, dd = [], [], []
for i in range(int(80 / DT)):
    if i * DT < 60:
        end = end + np.array([0.3, 0, 0]) * DT
    tt.payout(DT, end)
    tt.step(DT, end, water)
    if i % 12 == 0:
        tl.append(i * DT)
        ll.append(tt.length)
        dd.append(np.linalg.norm(end))
res["d_length_end_m"] = float(tt.length)
res["d_nodes_end"] = int(len(tt.X))
res["d_pass"] = bool(abs(tt.length - p["tether_length_max"]) < 1e-9 and max(ll) <= p["tether_length_max"] + 1e-9)
ax[2].plot(tl, ll, label="стравлено")
ax[2].plot(tl, dd, label="расстояние судно–аппарат")
ax[2].axhline(p["tether_length_max"], color="k", lw=0.5)
ax[2].set_xlabel("время, с")
ax[2].set_ylabel("м")
ax[2].set_title(f"(г) подача: {verdict(res['d_pass'])}", fontsize=8)
ax[2].legend()

# (д) Godot против эталона: тот же сценарий, что в physics_tests.gd (6 с, течение, подача)
end = np.array([6.0, 2.0, 7.0])
tt = Tether(p, [0, 0, 0], end, 11.0)
for i in range(240):          # 2 с: дальше трение покоя/скольжения раздувает разницу округлений (см. ниже)
    end = end + np.array([0.2, 0.1, 0.0]) * DT
    tt.payout(DT, end)
    tt.step(DT, end, lambda X: np.array([0.1, 0.05, 0.0]),
             lambda xo, xn: (np.array([xn[0], xn[1], 8.0]), np.array([0, 0, -1.0]), xn[2] - 8.0) if xn[2] > 8.0 else None)
gpath = OUT / "v2_godot_tether.csv"
if gpath.exists():
    g = np.loadtxt(gpath, delimiter=",", ndmin=2)
    head, nodes = g[0], g[1:]
    if nodes.shape[0] == len(tt.X):
        res["e_pos_err_m"] = float(np.max(np.abs(nodes[:, :3] - tt.X)))
        res["e_tension_err_N"] = float(np.max(np.abs(head[:3] - tt.tension_end)))
        res["e_pass"] = bool(res["e_pos_err_m"] < 1e-6 and res["e_tension_err_N"] < 1e-6)
    else:
        res["e_pass"] = False
        res["e_nodes"] = [int(nodes.shape[0]), len(tt.X)]
else:
    res["e_pass"] = False
    print("нет", gpath, "— сначала physics_tests.gd")

# (е) чувствительность: тот же сценарий 6 с, сдвиг одного узла на 1e-9 м
def _run(eps):
    e = np.array([6.0, 2.0, 7.0])
    q = Tether(p, [0, 0, 0], e, 11.0)
    q.X[5, 0] += eps
    out = []
    for i in range(720):
        e = e + np.array([0.2, 0.1, 0.0]) * DT
        q.payout(DT, e)
        q.step(DT, e, lambda X: np.array([0.1, 0.05, 0.0]),
               lambda xo, xn: (np.array([xn[0], xn[1], 8.0]), np.array([0, 0, -1.0]), xn[2] - 8.0) if xn[2] > 8.0 else None)
        if (i + 1) % 120 == 0:
            out.append(q.X.copy())
    return out


r0, r1 = _run(0.0), _run(1e-9)
res["f_sensitivity_m_per_s"] = [float(np.abs(x - y).max()) if x.shape == y.shape else None for x, y in zip(r0, r1)]

# (ж) формула Эйлера (канат на кнехте)
pc = dict(p)
pc["tether_seg"] = 0.05
Rb, rc = 0.1, 0.0035


def bar(xo, xn):
    d = np.array([xn[0], xn[2]])
    Lb = np.hypot(*d)
    if Lb < Rb + rc:
        n2 = d / max(Lb, 1e-9)
        q = n2 * (Rb + rc)
        return np.array([q[0], xn[1], q[1]]), np.array([n2[0], 0.0, n2[1]]), Rb + rc - Lb
    return None


Lc = 1.0 + np.pi * (Rb + rc)
tc = Tether(pc, [-(Rb + rc), 0, 0.5], [(Rb + rc), 0, 0.5], Lc)
sc = np.concatenate(([0.0], np.cumsum(tc.rest)))
pts = []
for si in sc:
    if si < 0.5:
        pts.append([-(Rb + rc), 0, 0.5 - si])
    elif si < 0.5 + np.pi * (Rb + rc):
        ang = np.pi - (si - 0.5) / (Rb + rc)
        pts.append([(Rb + rc) * np.cos(ang), 0, -(Rb + rc) * np.sin(ang)])
    else:
        pts.append([(Rb + rc), 0, si - 0.5 - np.pi * (Rb + rc)])
tc.X = np.array(pts)
tc.V[:] = 0
tc.anchor = tc.X[0].copy()
endc = tc.X[-1].copy()
dtc = 1 / 240
rat = []
for i in range(int(6 / dtc)):
    if i * dtc > 1.0:
        endc = endc + np.array([0, 0, 0.002]) * dtc
    tc.step(dtc, endc, None, bar)
    if i * dtc > 5.0:
        rat.append(np.linalg.norm(tc.tension_end) / tc.tension_top)
res["g_capstan_ratio"] = float(np.mean(rat))
res["g_capstan_euler"] = float(np.exp(p["tether_mu"] * np.pi))
res["g_mu_effective"] = float(np.log(np.mean(rat)) / np.pi)

fig.tight_layout()
fig.savefig(OUT / "v8_tether.png")
save_results("v8_tether", res)
for k, v in res.items():
    print(k, v)
print("V8:", verdict(all(res[k] for k in ("a_pass", "b_pass", "c_pass", "d_pass", "e_pass"))))
