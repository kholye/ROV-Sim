"""Ил, поднятый струями движителей у дна (облако взвеси из гауссовых клубов). NED, СИ.

Цепочка (docs/physics-sources.md, разд. 29):
1. Струя движителя: скорость на срезе насадки по теории импульса U0 = sqrt(2|T| / (rho A)),
   дальше круглая затопленная струя Albertson и др. 1950: на оси U_m = U0 до x = 6,2 D,
   дальше U_m = U0·6,2 D/x; поперёк гаусс u = U_m exp(-r²/(2σ²)), σ = 0,081 x (не уже D/4).
   Отсюда наибольшая скорость у дна под горизонтальной струёй 0,30·U0·D/h (как у Blaauw, van de Kaa 1978).
2. Касательное напряжение на дне tau = rho C_D u², размыв по Партениадесу E = M (tau/tau_ce - 1), tau > tau_ce.
3. Размытый ил копится и раз в EMIT_PERIOD выходит гауссовым клубом (масса, центр, σ по горизонтали — по пятну
   размыва, по вертикали — толщина струи над пятном, отражение от дна). Клуб несёт течение (профиль у дна) и поле струй; растёт вовлечением в струю
   (dσ/dt = 0,081·|u_струи|) и вихревой диффузией придонного слоя K = κ u* z (u* — от течения и от струй
   у дна под клубом, z — высота клуба + σ_z); центр оседает со скоростью w_s,
   масса уходит в дно потоком w_s·c(дно).
Числа: rov_params.json (thruster_duct_*, jet_*, silt_*). Свет облака — rov/light.py (silt_terms).
Модуль без движка: его порт godot/physics/silt_plume.gd.
"""
import numpy as np

from .dynamics import rot_nb
from .environment import bed_profile

EMIT_PERIOD = 0.3        # с: размытое за это время выходит одним клубом
MAX_PUFFS = 8            # больше клубов шейдер не считает (кадры/с): ближайшие сливаются
B_MIN = 1e-3             # 1/м: клуб с пиковым рассеянием меньше этого убирается (не виден)
KAPPA = 0.4              # постоянная Кармана
N_X = 24                 # точек вдоль струи
N_Y = 13                 # точек поперёк (±3σ)


def _phi(s):
    return np.exp(-0.5 * s * s) / np.sqrt(2.0 * np.pi)


class Puff:
    __slots__ = ("pos", "m", "sh", "sz", "age", "bed")

    def __init__(self, pos, m, sh, sz, bed, age=0.0):
        self.pos = np.array(pos, float)   # центр, NED
        self.m = float(m)                 # масса, кг
        self.sh = float(sh)               # σ по горизонтали, м
        self.sz = float(sz)               # σ по вертикали, м
        self.bed = float(bed)             # глубина дна под клубом (для отражения), м
        self.age = float(age)

    def peak_c(self):
        """Наибольшая концентрация (у центра, с отражением от дна не больше чем вдвое), кг/м³."""
        return self.m / ((2 * np.pi) ** 1.5 * self.sh ** 2 * self.sz)


class SiltPlume:
    def __init__(self, p, b_star=500.0):
        self.p = p
        self.b_star = b_star            # рассеяние на кг взвеси, м²/кг: только для отбора невидимых клубов
        self.puffs = []
        self.pending = np.zeros(2)      # накопленная масса по движителям, кг
        self.pend_pos = np.zeros((2, 3))
        self.pend_s2 = np.zeros(2)
        self.pend_sg = np.zeros(2)
        self.pend_t = np.zeros(2)
        self.eroded = 0.0               # баланс масс: размыто = во взвеси + осело + убрано
        self.deposited = 0.0
        self.removed = 0.0
        D = p["thruster_duct_d"]
        self.A = np.pi * D * D / 4.0
        self.box = None                 # стенки (бассейн): (север мин, север макс, восток мин, восток макс), м
        # последний размыв по струям (для частиц-хлопьев): кг/с, центр NED, дисперсия по площади, толщина струи
        self.last = [(0.0, np.zeros(3), 0.0, 0.0), (0.0, np.zeros(3), 0.0, 0.0)]

    # ---------------- струи ----------------

    def jets(self, x, thr):
        """Струи движителей: [(срез NED, направление NED, U0, D)] для движителей с тягой."""
        p = self.p
        R = rot_nb(*x[3:6])
        tp = np.array(p["thruster_pos"], float)
        out = []
        for k, sgn in enumerate((-1.0, 1.0)):        # левый (y < 0), правый
            s = float(np.clip(thr[k], -1.0, 1.0))
            T = p["thrust_max"] * s * abs(s)
            if T < 0:
                T *= p["thrust_reverse_ratio"]
            if T == 0.0:
                out.append(None)
                continue
            pos_b = np.array([tp[0], sgn * tp[1], tp[2]])
            d_b = np.array([-np.sign(T), 0.0, 0.0])  # тяга вперёд — струя назад
            outlet_b = pos_b + d_b * p["thruster_duct_length"] / 2.0
            U0 = np.sqrt(2.0 * abs(T) / (p["rho"] * self.A))
            out.append((x[0:3] + R @ outlet_b, R @ d_b, U0, p["thruster_duct_d"]))
        return out

    def axis_speed(self, xa, U0, D):
        """Скорость на оси и полуширина σ на расстоянии xa от среза."""
        core = self.p["jet_core"] * D
        Um = U0 if xa <= core else U0 * core / xa
        sig = max(self.p["jet_spread"] * xa, D / 4.0)
        return Um, sig

    def jet_velocity(self, X, jets):
        """Скорость, наведённая струями в точке X (NED), м/с."""
        v = np.zeros(3)
        for j in jets:
            if j is None:
                continue
            o, d, U0, D = j
            rel = X - o
            xa = rel @ d
            if xa <= 0.0:
                continue
            r2 = rel @ rel - xa * xa
            Um, sig = self.axis_speed(xa, U0, D)
            v += d * Um * np.exp(-r2 / (2 * sig * sig))
        return v

    def bed_speed(self, xa, h, U0, D):
        """Скорость у дна прямо под осью струи (h — высота оси над дном)."""
        Um, sig = self.axis_speed(xa, U0, D)
        return Um * np.exp(-h * h / (2 * sig * sig))

    def erosion(self, jet, bed):
        """Размыв дна (глубина bed) одной струёй: (кг/с, центр размыва NED, дисперсия по площади м², толщина струи σ
        над размывом, м — сорванный ил сразу уходит в турбулентную струю и занимает её толщину)."""
        p = self.p
        o, d, U0, D = jet
        dh = np.array([d[0], d[1], 0.0])
        nh = np.linalg.norm(dh)
        if nh < 1e-6:
            return 0.0, o, 0.0, 0.0
        e = dh / nh
        n = np.array([-e[1], e[0], 0.0])              # поперёк, горизонтально
        xs = np.geomspace(0.05, 5.0, N_X)
        edges = np.concatenate(([0.0], 0.5 * (xs[1:] + xs[:-1]), [xs[-1] * 1.05]))
        tot = 0.0
        acc_sig = 0.0
        acc = np.zeros(3)
        acc2 = 0.0
        pts = []
        for i, xa in enumerate(xs):
            A = o + d * xa
            h = bed - A[2]
            if h < 0.0:                               # струя упёрлась в дно: дальше не идёт
                break
            Um, sig = self.axis_speed(xa, U0, D)
            ys = np.linspace(-3 * sig, 3 * sig, N_Y)
            dy = ys[1] - ys[0]
            u = Um * np.exp(-(h * h + ys * ys) / (2 * sig * sig))
            tau = p["rho"] * p["silt_cd_bed"] * u * u
            E = p["silt_M"] * np.maximum(tau / p["silt_tau_ce"] - 1.0, 0.0)
            dm = E * dy * (edges[i + 1] - edges[i]) * nh
            if not np.any(dm > 0):
                continue
            base = np.array([A[0], A[1], bed])
            for y, w in zip(ys, dm):
                if w > 0:
                    P = base + n * y
                    pts.append((P, w))
                    tot += w
                    acc += w * P
                    acc_sig += w * sig
        if tot <= 0.0:
            return 0.0, o, 0.0, 0.0
        c = acc / tot
        for P, w in pts:
            acc2 += w * np.sum((P - c) ** 2)
        return tot, c, acc2 / tot, acc_sig / tot

    # ---------------- шаг ----------------

    def step(self, dt, x, thr, beds, current=None, h_site=0.0):
        """dt, с; x — состояние аппарата (14); thr — команды движителей; beds — глубина дна под каждым
        движителем, м (nan — дна нет); current — RovEnvironment.Current или None, h_site — глубина места для профиля."""
        p = self.p
        jets = self.jets(x, thr)
        for k in range(2):
            self.last[k] = (0.0, np.zeros(3), 0.0, 0.0)
            if jets[k] is not None and np.isfinite(beds[k]):
                mdot, c, s2, sg = self.erosion(jets[k], beds[k])
                self.last[k] = (mdot, c, s2, sg)
                if mdot > 0:
                    dm = mdot * dt
                    w0 = self.pending[k]
                    self.pend_pos[k] = (w0 * self.pend_pos[k] + dm * c) / (w0 + dm)
                    self.pend_s2[k] = (w0 * self.pend_s2[k] + dm * s2) / (w0 + dm)
                    self.pend_sg[k] = (w0 * self.pend_sg[k] + dm * sg) / (w0 + dm)
                    self.pending[k] += dm
                    self.eroded += dm
            self.pend_t[k] += dt
            if self.pend_t[k] >= EMIT_PERIOD:
                self.pend_t[k] = 0.0
                if self.pending[k] > 0:
                    sh = max(np.sqrt(self.pend_s2[k] / 2.0), p["silt_sigma0"])
                    sz = max(self.pend_sg[k], p["silt_sigma0"])
                    self.puffs.append(Puff(self.pend_pos[k], self.pending[k], sh, sz, self.pend_pos[k][2]))
                    self.pending[k] = 0.0
                    self.pend_s2[k] = 0.0
        U = 0.0
        if current is not None:
            U = np.linalg.norm(current.velocity())
        ustar = np.sqrt(p["silt_cd_current"]) * U
        ws = p["silt_ws"]
        keep = []
        for f in self.puffs:
            hgt = max(f.bed - f.pos[2], 0.0)
            vc = current.velocity_at(hgt, h_site) if current is not None else np.zeros(3)
            vj = self.jet_velocity(f.pos, jets)
            f.pos = f.pos + (vc + vj) * dt
            f.pos[2] = min(f.pos[2] + ws * dt, f.bed)
            # турбулентность у дна: течение и струи над клубом (то же u у дна, что размывает ил)
            ub = np.linalg.norm(self.jet_velocity(np.array([f.pos[0], f.pos[1], f.bed]), jets))
            us = np.sqrt(ustar * ustar + p["silt_cd_bed"] * ub * ub)
            K = KAPPA * us * max(hgt + f.sz, 0.05)
            grow = p["jet_spread"] * np.linalg.norm(vj) * dt
            f.sh = np.sqrt((f.sh + grow) ** 2 + 2 * K * dt)
            f.sz = np.sqrt((f.sz + grow) ** 2 + 2 * K * dt)
            if self.box is not None:
                self._confine(f)
            hgt = max(f.bed - f.pos[2], 0.0)
            lost = f.m * (1.0 - np.exp(-ws * 2.0 * _phi(hgt / f.sz) / f.sz * dt))
            f.m -= lost
            self.deposited += lost
            f.age += dt
            if f.peak_c() * 2.0 * self.b_star < B_MIN:
                self.removed += f.m
            else:
                keep.append(f)
        self.puffs = keep
        while len(self.puffs) > MAX_PUFFS:
            self._merge_closest()

    def _confine(self, f):
        """Бассейн: центр клуба не выходит за стенки, σ по горизонтали не больше половины ширины, по вертикали —
        половины глубины (грубо: ил остаётся в бассейне, отражения от стенок не считаются)."""
        n0, n1, e0, e1 = self.box
        f.pos[0] = min(max(f.pos[0], n0), n1)
        f.pos[1] = min(max(f.pos[1], e0), e1)
        f.sh = min(f.sh, 0.5 * min(n1 - n0, e1 - e0))
        f.sz = min(f.sz, 0.5 * f.bed)

    def _merge_closest(self):
        best, bi, bj = np.inf, 0, 1
        for i in range(len(self.puffs)):
            for j in range(i + 1, len(self.puffs)):
                a, b = self.puffs[i], self.puffs[j]
                d2 = np.sum((a.pos - b.pos) ** 2) / (a.sh ** 2 + b.sh ** 2 + a.sz ** 2 + b.sz ** 2)
                if d2 < best:
                    best, bi, bj = d2, i, j
        a, b = self.puffs[bi], self.puffs[bj]
        self.puffs[bi] = merge(a, b)
        del self.puffs[bj]

    def concentration(self, X):
        """Концентрация ила в точке X (NED), кг/м³ (с отражением от дна)."""
        c = 0.0
        for f in self.puffs:
            norm = f.m / ((2 * np.pi) ** 1.5 * f.sh ** 2 * f.sz)
            dh2 = (X[0] - f.pos[0]) ** 2 + (X[1] - f.pos[1]) ** 2
            for zc in (f.pos[2], 2 * f.bed - f.pos[2]):
                c += norm * np.exp(-0.5 * (dh2 / f.sh ** 2 + (X[2] - zc) ** 2 / f.sz ** 2))
        return c

    def suspended(self):
        return sum(f.m for f in self.puffs) + float(np.sum(self.pending))


def merge(a, b):
    """Один клуб с той же массой, центром масс и вторыми моментами (по горизонтали — среднее двух осей)."""
    m = a.m + b.m
    c = (a.m * a.pos + b.m * b.pos) / m
    def mom_h(f):
        d = f.pos[:2] - c[:2]
        return f.m * (f.sh ** 2 + (d @ d) / 2.0)
    def mom_z(f):
        return f.m * (f.sz ** 2 + (f.pos[2] - c[2]) ** 2)
    sh = np.sqrt((mom_h(a) + mom_h(b)) / m)
    sz = np.sqrt((mom_z(a) + mom_z(b)) / m)
    return Puff(c, m, sh, sz, (a.m * a.bed + b.m * b.bed) / m, (a.m * a.age + b.m * b.age) / m)
