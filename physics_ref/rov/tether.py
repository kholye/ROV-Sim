"""Кабель-трос ТНПА: цепочка сосредоточенных масс (NED, СИ). Источники: docs/physics-sources.md, разд. 30.

Модель (сосредоточенные массы, как у Driscoll, Lueck, Nahon 2000; Buckham 2003 для слабо натянутых тросов):
- узлы с массой кабеля и присоединённой массой воды, вес в воде (тонет), сопротивление по Морисону раздельно
  поперёк (C_n по диаметру) и вдоль (C_t по смоченному периметру) относительно течения; сопротивление явное
  с ограничением: за шаг относительная скорость не меняет знак (устойчиво; в равновесии сила точная — неявная
  схема занижала её на ~15 % при шаге 1/120 с);
- звенья почти нерастяжимы (упругость меди EA) и работают только на растяжение (сжатое звено — изгиб кабеля
  между узлами): ограничения длины решаются XPBD (Macklin и др. 2016) с точным решением трёхдиагональной
  системы на каждой итерации Ньютона (цепочка: матрица J·W·Jᵀ трёхдиагональна), λ ≤ 0;
- верхний узел — блок на судне обеспечения, нижний — гермоввод аппарата (оба задаются извне);
- касания с дном и судном — функция contact (мост движка): возвращает узел вне препятствия, нормаль и глубину;
  трение Кулона по смещению вдоль поверхности (позиционное трение XPBD);
- подача: длина стравленного кабеля меняется у судна (верхнее звено переменной длины, узлы добавляются и
  убираются там же); помощник держит слабину и стравливает, когда кабель натянут.
Натяжение у аппарата — множитель Лагранжа последнего звена / dt²: это сила на аппарат (rov/dynamics.py, ext).
Порт: godot/physics/tether_cable.gd.
"""
import numpy as np

NEWTON = 3               # итераций Ньютона на шаг (трёхдиагональная система — точно на каждой)


class Tether:
    def __init__(self, p, anchor, end, length):
        self.p = p
        self.seg = p["tether_seg"]
        rho = p["rho"]
        self.w_net = (p["tether_mass_per_m"] - rho * p["tether_area"]) * p["g"]   # Н/м, вниз (+z)
        self.mu_m = p["tether_mass_per_m"] + rho * p["tether_area"] * p["tether_ca"]  # масса с присоединённой, кг/м
        self.kn = 0.5 * rho * p["tether_cn"] * p["tether_d_drag"]                 # Н·с²/м³ на метр
        self.kt = 0.5 * rho * p["tether_ct"] * np.pi * p["tether_d_drag"]
        self.anchor = np.array(anchor, float)
        self.length = float(length)
        self.tension_end = np.zeros(3)   # сила кабеля на аппарат, NED, Н
        self.tension_top = 0.0
        self.taut = False
        self._init_shape(np.array(end, float))

    # ---------------- форма ----------------

    def _init_shape(self, end):
        """Узлы по дуге с провисом вниз так, чтобы длина дуги была length; верхнее звено — остаток."""
        n_full = max(int(np.floor(self.length / self.seg)), 1)
        l0 = self.length - (n_full - 1) * self.seg
        if l0 < 0.3 * self.seg and n_full > 1:
            n_full -= 1
            l0 += self.seg
        self.rest = np.array([l0] + [self.seg] * (n_full - 1))
        N = len(self.rest) + 1
        a, b = self.anchor, end
        d = np.linalg.norm(b - a)
        u = np.linspace(0.0, 1.0, 401)
        sag = 0.0
        for _ in range(60):              # провис h: длина дуги a + h·4u(1−u) вниз = length
            curve = a + (b - a) * u[:, None]
            curve[:, 2] += sag * 4 * u * (1 - u)
            arc = np.concatenate(([0.0], np.cumsum(np.linalg.norm(np.diff(curve, axis=0), axis=1))))
            if arc[-1] >= self.length or d >= self.length:
                break
            sag += max(0.5 * (self.length - arc[-1]), 0.01)
        # узлы по длине дуги (звенья сразу почти нужной длины; если дуга короче — сжаты, это изгиб)
        s_nodes = np.concatenate(([0.0], np.cumsum(self.rest))) * (arc[-1] / self.length)
        pts = np.stack([np.interp(s_nodes, arc, curve[:, k]) for k in range(3)], axis=1)
        self.X = pts
        self.V = np.zeros((N, 3))

    def total_length(self):
        return float(np.sum(self.rest))

    # ---------------- подача ----------------

    def payout(self, dt, end):
        """Помощник на судне: держит стравленным slack[0]·d + slack[1]; стравливает при натяжении > taut; выбирает только
        слабину — тем медленнее, чем ближе натяжение у блока к весу висящего кабеля + запас (аппарат не тянет)."""
        p = self.p
        d = np.linalg.norm(end - self.anchor)
        k, add = p["tether_slack"]
        target = min(p["tether_length_max"], max(k * d + add, d + self.seg))
        v = p["tether_payout_speed"]
        rate = v * np.clip((target - self.length) / 1.0, -1.0, 1.0)
        if rate < 0.0:                    # выбирает только слабину: натяжение у блока не больше веса висящего кабеля + запас
            slack_T = self.w_net * max(end[2] - self.anchor[2], 0.0) + p["tether_haul_margin"]
            rate *= np.clip(1.0 - self.tension_top / slack_T, 0.0, 1.0)
        if self.tension_top > p["tether_taut"]:
            rate = v
        new_len = min(max(self.length + rate * dt, 2 * self.seg), p["tether_length_max"])
        self.rest[0] += new_len - self.length
        self.length = new_len
        while self.rest[0] > 1.5 * self.seg:                 # стравили: новый узел у судна
            f = (self.rest[0] - self.seg) / self.rest[0]
            Xn = self.anchor + (self.X[1] - self.anchor) * f
            Vn = self.V[1] * f
            self.X = np.insert(self.X, 1, Xn, axis=0)
            self.V = np.insert(self.V, 1, Vn, axis=0)
            self.rest = np.insert(self.rest, 1, self.seg)
            self.rest[0] -= self.seg
        while self.rest[0] < 0.3 * self.seg and len(self.rest) > 2:   # выбрали: узел у судна убран
            self.X = np.delete(self.X, 1, axis=0)
            self.V = np.delete(self.V, 1, axis=0)
            self.rest[0] += self.rest[1]
            self.rest = np.delete(self.rest, 1)

    # ---------------- шаг ----------------

    def node_mass(self):
        l = self.rest
        L = np.zeros(len(l) + 1)
        L[:-1] += 0.5 * l
        L[1:] += 0.5 * l
        return L

    def step(self, dt, end, water=None, contact=None):
        """dt, с; end — гермоввод аппарата (NED); water(X) -> скорость воды (NED); contact(x_old, x_new) ->
        (x, нормаль, глубина) или None."""
        p = self.p
        N = len(self.X)
        Lm = self.node_mass()
        m = self.mu_m * Lm
        X, V = self.X, self.V
        P = X.copy()
        for i in range(1, N - 1):
            t = X[i + 1] - X[i - 1]
            t = t / max(np.linalg.norm(t), 1e-9)
            # сопротивление по скорости в начале шага (иначе оно гасит разгон от веса за шаг — ложная подъёмная сила)
            u = water(X[i]) if water is not None else np.zeros(3)
            vr = V[i] - u
            vt = (vr @ t) * t
            vn = vr - vt
            dvn = -vn * min(dt * self.kn * Lm[i] * np.linalg.norm(vn) / m[i], 1.0)
            dvt = -vt * min(dt * self.kt * Lm[i] * np.linalg.norm(vt) / m[i], 1.0)
            V[i] = V[i] + dvn + dvt
            V[i, 2] += dt * self.w_net * Lm[i] / m[i]
            P[i] = X[i] + dt * V[i]
        P[0] = self.anchor
        P[N - 1] = end
        w = 1.0 / m
        w[0] = 0.0
        w[N - 1] = 0.0
        alpha = self.rest / (p["tether_EA"] * dt * dt)
        lam = np.zeros(N - 1)
        contacts = {}
        for it in range(NEWTON + 1):
            self._solve(P, w, alpha, lam)
            if contact is not None:
                for i in range(1, N - 1):
                    r = contact(X[i], P[i])
                    if r is not None:
                        P[i] = r[0]
                        contacts[i] = (r[1], contacts.get(i, (None, 0.0))[1] + r[2])
        # трение: смещение вдоль поверхности за шаг не больше μ·(глубина выталкивания)
        mu = p["tether_mu"]
        for i, (n, depth) in contacts.items():
            dlt = P[i] - X[i]
            tang = dlt - (dlt @ n) * n
            tl = np.linalg.norm(tang)
            if tl <= mu * depth:
                P[i] -= tang
            elif tl > 0:
                P[i] -= tang * (mu * depth / tl)
        self.V[1:N - 1] = (P[1:N - 1] - X[1:N - 1]) / dt
        self.X = P
        nl = P[N - 1] - P[N - 2]
        nl /= max(np.linalg.norm(nl), 1e-12)
        # на аппарат: натяжение последнего звена + вес в воде половины звена у гермоввода (масса узла на нём)
        self.tension_end = lam[N - 2] * nl / (dt * dt) + np.array([0.0, 0.0, self.w_net * Lm[N - 1]])
        self.tension_top = float(-lam[0] / (dt * dt))
        self.taut = bool(self.length >= p["tether_length_max"] - 1e-9 and np.linalg.norm(self.tension_end) > p["tether_taut"])
        self.contacts = sorted(contacts)

    def _solve(self, P, w, alpha, lam):
        """Одна итерация Ньютона XPBD: J W Jᵀ Δλ = −C − α̃λ (трёхдиагональная система, прогонка), затем смещения."""
        M = len(self.rest)
        d = P[1:] - P[:-1]
        L = np.linalg.norm(d, axis=1)
        n = d / np.maximum(L, 1e-12)[:, None]
        C = L - self.rest
        # звено только тянет: сжатое звено без натяжения не участвует (кабель изгибается между узлами)
        act = (C > 0) | (lam < 0)
        diag = np.where(act, w[:-1] + w[1:] + alpha, 1.0)
        off = -w[1:M] * np.sum(n[:-1] * n[1:], axis=1) * (act[:-1] & act[1:])   # связь звеньев j, j+1 через узел j+1
        b = np.where(act, -C - alpha * lam, 0.0)
        # прогонка (Томас)
        cp = np.zeros(M)
        dp = np.zeros(M)
        cp[0] = off[0] / diag[0] if M > 1 else 0.0
        dp[0] = b[0] / diag[0]
        for j in range(1, M):
            den = diag[j] - off[j - 1] * cp[j - 1]
            cp[j] = off[j] / den if j < M - 1 else 0.0
            dp[j] = (b[j] - off[j - 1] * dp[j - 1]) / den
        dl = np.zeros(M)
        dl[M - 1] = dp[M - 1]
        for j in range(M - 2, -1, -1):
            dl[j] = dp[j] - cp[j] * dl[j + 1]
        dl = np.minimum(dl, -lam)            # λ + Δλ ≤ 0: звено только тянет
        lam += dl
        P[:-1] -= (w[:-1] * dl)[:, None] * n
        P[1:] += (w[1:] * dl)[:, None] * n
