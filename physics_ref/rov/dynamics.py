"""Динамика аппарата, 6 степеней свободы по Fossen (2011), система NED.

Состояние x (14):
  0-5   eta = (x, y, z, phi, theta, psi)   положение в NED, м; углы Эйлера ZYX, рад
  6-11  nu  = (u, v, w, p, q, r)           скорости в осях тела, м/с и рад/с
  12-13 V1, V2                             вода в цистернах 1 (носовая) и 2 (кормовая), м3

Уравнение (Fossen 2011, разд. 10.3, с течением):
  M_RB nu' + M_A nu_r' + C_RB(nu) nu + C_A(nu_r) nu_r + D(nu_r) nu_r + g(eta) = tau
  nu_r = nu - nu_c, течение постоянно в NED на шаге интегрирования.

Только чистые функции и числа: без движка, без глобального состояния.
"""
import numpy as np


def skew(a):
    return np.array([[0.0, -a[2], a[1]], [a[2], 0.0, -a[0]], [-a[1], a[0], 0.0]])


def rot_nb(phi, theta, psi):
    """Матрица поворота тело -> NED (Fossen 2011, ф. 2.18)."""
    cf, sf = np.cos(phi), np.sin(phi)
    ct, st = np.cos(theta), np.sin(theta)
    cp, sp = np.cos(psi), np.sin(psi)
    return np.array([
        [cp * ct, -sp * cf + cp * st * sf, sp * sf + cp * cf * st],
        [sp * ct, cp * cf + sf * st * sp, -cp * sf + st * sp * cf],
        [-st, ct * sf, ct * cf],
    ])


def t_theta(phi, theta):
    """Связь угловых скоростей тела с производными углов Эйлера (Fossen 2011, ф. 2.29)."""
    cf, sf = np.cos(phi), np.sin(phi)
    ct, tt = np.cos(theta), np.tan(theta)
    return np.array([[1.0, sf * tt, cf * tt], [0.0, cf, -sf], [0.0, sf / ct, cf / ct]])


def coriolis(M, nu):
    """C(nu) по матрице масс (Fossen 2011, ф. 6.43), годится и для M_RB, и для M_A."""
    n1, n2 = nu[:3], nu[3:]
    a = M[:3, :3] @ n1 + M[:3, 3:] @ n2
    b = M[3:, :3] @ n1 + M[3:, 3:] @ n2
    C = np.zeros((6, 6))
    C[:3, 3:] = -skew(a)
    C[3:, :3] = -skew(a)
    C[3:, 3:] = -skew(b)
    return C


def lamb_k(L, D):
    """Коэффициенты Лэмба вытянутого эллипсоида вращения: k1 (вдоль), k2 (поперёк), k' (поворот)."""
    a, b = L / 2.0, D / 2.0
    e = np.sqrt(1.0 - (b / a) ** 2)
    ln = np.log((1 + e) / (1 - e))
    alpha0 = 2.0 * (1 - e ** 2) / e ** 3 * (0.5 * ln - e)
    beta0 = 1.0 / e ** 2 - (1 - e ** 2) / (2 * e ** 3) * ln
    k1 = alpha0 / (2 - alpha0)
    k2 = beta0 / (2 - beta0)
    kr = e ** 4 * (beta0 - alpha0) / ((2 - e ** 2) * (2 * e ** 2 - (2 - e ** 2) * (beta0 - alpha0)))
    return k1, k2, kr


def added_mass_matrix(p):
    """Матрица присоединённых масс 6×6 по полосовой теории (Fossen 2011, гл. 6; Newman 1977, разд. 4).

    Каждая полоса: участок x0..x1 с осью в точке (y, z) тела и двумерными присоединёнными массами
    rho*s22 (поперёк, по y), rho*s33 (по z), rho*s44 (крен) на метр длины. Скорость полосы по y и z:
      v_l = v + r x - p z = J2·nu,  J2 = [0, 1, 0, -z, 0, x]
      w_l = w + p y - q x = J3·nu,  J3 = [0, 0, 1, y, -x, 0]
    Кинетическая энергия 1/2 rho (s22 v_l² + s33 w_l² + s44 p²) даёт M_A = ∫ rho (s22 J2ᵀJ2 + s33 J3ᵀJ3) dx
    плюс s44 в (3, 3). Продольная масса added_mass_surge (Лэмб) отдельно. Матрица симметрична.
    """
    rho = p["rho"]
    MA = np.zeros((6, 6))
    MA[0, 0] = p["added_mass_surge"]
    for s in p["added_mass_strips"]:
        x0, x1, y, z = s["x0"], s["x1"], s["y"], s["z"]
        L = x1 - x0
        X1 = (x1 ** 2 - x0 ** 2) / 2.0
        X2 = (x1 ** 3 - x0 ** 3) / 3.0
        a, b = rho * s["s22"], rho * s["s33"]
        # J2ᵀJ2: индексы 1, 3, 5
        MA[1, 1] += a * L
        MA[1, 3] += -a * z * L
        MA[1, 5] += a * X1
        MA[3, 3] += a * z * z * L
        MA[3, 5] += -a * z * X1
        MA[5, 5] += a * X2
        # J3ᵀJ3: индексы 2, 3, 4
        MA[2, 2] += b * L
        MA[2, 3] += b * y * L
        MA[2, 4] += -b * X1
        MA[3, 3] += b * y * y * L
        MA[3, 4] += -b * y * X1
        MA[4, 4] += b * X2
        MA[3, 3] += rho * s["s44"] * L
    iu = np.triu_indices(6, 1)
    MA[(iu[1], iu[0])] = MA[iu]
    return MA


def submerged_fraction(z_axis, r):
    """Доля площади круга радиуса r под водой, если ось трубы на глубине z_axis (z вниз)."""
    h = min(max(z_axis + r, 0.0), 2.0 * r)
    if h <= 0.0:
        return 0.0
    if h >= 2.0 * r:
        return 1.0
    seg = r * r * np.arccos((r - h) / r) - (r - h) * np.sqrt(2 * r * h - h * h)
    return seg / (np.pi * r * r)


class Vehicle:
    """Постоянные модели, посчитанные из параметров один раз."""

    def __init__(self, p):
        self.p = p
        rho = p["rho"]
        self.r = p["hull_diameter"] / 2.0      # только для выхода на поверхность (габарит фланцев)
        # Присоединённые массы: полосы по деталям модели (added_mass_matrix), полная матрица 6×6.
        self.MA = added_mass_matrix(p)
        # Сопротивление: продольное по лобовой площади в её центре, поперечное по клеткам силуэтов
        # (принцип поперечного обтекания, cross-flow drag: Hoerner 1965, гл. 3; Fossen 2011, гл. 6).
        self.k_front = 0.5 * rho * p["cd_axial"] * p["drag_area_front"]
        self.front_c = np.asarray(p["drag_front_center"], dtype=float)     # (y, z)
        self.k_cr = 0.5 * rho * p["cd_cross"]
        self.side = np.asarray(p["drag_cells_side"], dtype=float)          # (x, z, A): вид сбоку
        self.top = np.asarray(p["drag_cells_top"], dtype=float)            # (x, y > 0, A): правая половина
        xs, zs, As = self.side.T
        xt, yt, At = self.top.T
        At = 2 * At                                                         # с зеркальной половиной
        # Равносильная диагональ: сила при движении по одной оси (для аналитических проверок V1).
        self.d_quad = np.array([
            self.k_front,
            self.k_cr * As.sum(),
            self.k_cr * At.sum(),
            self.k_cr * ((As * np.abs(zs) ** 3).sum() + (At * np.abs(yt) ** 3).sum()),
            self.k_cr * (At * np.abs(xt) ** 3).sum(),
            self.k_cr * (As * np.abs(xs) ** 3).sum(),
        ])
        # линейное: по вертикали трос и трение (подогнано по рис. 48 Дунаева), крен (оценка)
        self.d_lin = np.array([0.0, 0.0, p["heave_damping_lin"], p["roll_damping_lin"], 0.0, 0.0])
        tx, ty, tz = p["thruster_pos"]
        self.thr_pos = np.array([[tx, -ty, tz], [tx, ty, tz]])   # левый, правый
        self.tank_pos = np.array([[p["tank_x"][0], 0.0, 0.0], [p["tank_x"][1], 0.0, 0.0]])
        self.fins = p["fins"]

    # ---- массы ----
    def mass_props(self, V1, V2, dropped):
        """Масса, центр масс и M_RB. При сбросе груза его масса и момент инерции вычитаются в точке
        ballast_drop_pos, поэтому центр масс поднимается."""
        p = self.p
        rho = p["rho"]
        m0, cg0 = p["mass_dry"], np.array(p["cg_dry"])
        # инерция сухого аппарата относительно начала координат тела
        I = np.diag(p["inertia_dry_cg"]) + m0 * (cg0 @ cg0 * np.eye(3) - np.outer(cg0, cg0))
        if dropped:
            md, rd = p["ballast_drop_mass"], np.array(p["ballast_drop_pos"])
            m_body = m0 - md
            cg_body = (m0 * cg0 - md * rd) / m_body
            I = I - md * (rd @ rd * np.eye(3) - np.outer(rd, rd))
        else:
            m_body, cg_body = m0, cg0
        mw = rho * np.array([V1, V2])
        m = m_body + mw.sum()
        rg = (m_body * cg_body + mw @ self.tank_pos) / m
        for k in range(2):                     # вода в цистернах точками
            rk = self.tank_pos[k]
            I = I + mw[k] * (rk @ rk * np.eye(3) - np.outer(rk, rk))
        MRB = np.zeros((6, 6))
        MRB[:3, :3] = m * np.eye(3)
        MRB[:3, 3:] = -m * skew(rg)
        MRB[3:, :3] = m * skew(rg)
        MRB[3:, 3:] = I
        return m, rg, MRB

    def displaced_volume(self, dropped):
        p = self.p
        return p["mass_dry"] / p["rho"] + p["neutral_tank_volume"] - (p["ballast_drop_volume"] if dropped else 0.0)

    def buoyancy_center(self, dropped):
        """Центр плавучести; после сброса груза без объёма груза."""
        p = self.p
        cb = np.array(p["cb"], dtype=float)
        if not dropped:
            return cb
        V, Vd = self.displaced_volume(False), p["ballast_drop_volume"]
        return (V * cb - Vd * np.array(p["ballast_drop_pos"])) / (V - Vd)

    # ---- силы ----
    def restoring(self, eta, W, B, rg, rb):
        phi, theta = eta[3], eta[4]
        cf, sf, ct, st = np.cos(phi), np.sin(phi), np.cos(theta), np.sin(theta)
        xg, yg, zg = rg
        xb, yb, zb = rb
        return np.array([
            (W - B) * st,
            -(W - B) * ct * sf,
            -(W - B) * ct * cf,
            -(yg * W - yb * B) * ct * cf + (zg * W - zb * B) * ct * sf,
            (zg * W - zb * B) * st + (xg * W - xb * B) * ct * cf,
            -(xg * W - xb * B) * ct * sf - (yg * W - yb * B) * st,
        ])

    def thrust(self, s):
        """s = (левый, правый) в [-1, 1]. Тяга T = Tmax s|s| (оценка: ШИМ ~ обороты, T ~ n²)."""
        p = self.p
        tau = np.zeros(6)
        forces = []
        for k in range(2):
            sk = float(np.clip(s[k], -1.0, 1.0))
            T = p["thrust_max"] * sk * abs(sk)
            if T < 0:
                T *= p["thrust_reverse_ratio"]
            F = np.array([T, 0.0, 0.0])
            tau[:3] += F
            tau[3:] += np.cross(self.thr_pos[k], F)
            forces.append(T)
        return tau, forces

    def fin_forces(self, nu_r):
        """Плоскости и насадки: сила вдоль нормали n (ось y или z тела) в точке r.

        Местная скорость v = nu_r[:3] + omega x r; угол атаки alpha = c/|u|, c = v[n], u = v[0].
        Подъёмная сила (малые углы, как у рулей в Fossen 2011): L = -1/2 rho A C_La |u| c,
        |c| ограничена tan(alpha_stall)|u| (срыв). Плюс сопротивление пластины поперёк потока:
        -1/2 rho A Cd |c| c. Обе части только гасят движение (работа <= 0).
        """
        rho = self.p["rho"]
        tau = np.zeros(6)
        for f in self.fins:
            r = np.asarray(f["pos"], dtype=float)
            n = f["normal"]
            v = nu_r[:3] + np.cross(nu_r[3:], r)
            u, c = v[0], v[n]
            k = np.tan(np.radians(f["alpha_stall_deg"])) * abs(u)
            c_lift = min(max(c, -k), k)
            F = -0.5 * rho * f["area"] * (f["cla"] * abs(u) * c_lift + f["cd_plate"] * abs(c) * c)
            Fv = np.zeros(3)
            Fv[n] = F
            tau[:3] += Fv
            tau[3:] += np.cross(r, Fv)
        return tau

    def drag(self, nu_r):
        """Квадратичное сопротивление по силуэтам модели (только гасит движение).

        Продольное: F_x = -k_front |u_l| u_l в центре лобовой площади (y_c, z_c), u_l = u + q z_c - r y_c.
        Поперечное (cross-flow): каждая клетка силуэта площадью A получает F = -1/2 rho Cd A |v_l| v_l
        от своей местной скорости: сбоку v_l = v + r x - p z, сверху w_l = w + p y - q x.
        Отсюда же моменты по крену, дифференту и курсу, в том числе от смещения силуэта вниз.
        """
        u, v, w, pr, q, r = nu_r
        tau = np.zeros(6)
        yc, zc = self.front_c
        ul = u + q * zc - r * yc
        Fx = -self.k_front * abs(ul) * ul
        tau[0] += Fx
        tau[4] += zc * Fx
        tau[5] += -yc * Fx
        x, z, A = self.side.T
        vl = v + r * x - pr * z
        Fy = -self.k_cr * A * np.abs(vl) * vl
        tau[1] += Fy.sum()
        tau[3] += -(z * Fy).sum()
        tau[5] += (x * Fy).sum()
        # сверху: клетка (x, y) и её зеркальная (x, -y) попарно, чтобы симметрия была точной
        x, y, A = self.top.T
        wp = w + pr * y - q * x
        wm = w - pr * y - q * x
        Fp = -self.k_cr * A * np.abs(wp) * wp
        Fm = -self.k_cr * A * np.abs(wm) * wm
        tau[2] += (Fp + Fm).sum()
        tau[3] += (y * (Fp - Fm)).sum()
        tau[4] += -(x * (Fp + Fm)).sum()
        return tau

    # ---- полная производная ----
    def deriv(self, x, thr, tank_cmd, vc_n=(0.0, 0.0, 0.0), dropped=False, ext=None):
        """Производная состояния и nu' (для акселерометра).
        ext — внешняя сила (кабель-трос): (сила в NED, Н; точка приложения в осях тела, м) или None."""
        p = self.p
        eta, nu = x[:6], x[6:12]
        V1, V2 = x[12], x[13]
        R = rot_nb(eta[3], eta[4], eta[5])
        m, rg, MRB = self.mass_props(V1, V2, dropped)
        W = m * p["g"]
        f_sub = submerged_fraction(eta[2], self.r)
        B = p["rho"] * p["g"] * self.displaced_volume(dropped) * f_sub
        rb = self.buoyancy_center(dropped)

        vc_b = R.T @ np.asarray(vc_n, dtype=float)
        nu_c = np.concatenate([vc_b, np.zeros(3)])
        nu_r = nu - nu_c
        nudot_c = np.concatenate([-skew(nu[3:]) @ vc_b, np.zeros(3)])

        tau, _ = self.thrust(thr)
        if ext is not None:
            Fb = R.T @ np.asarray(ext[0], dtype=float)
            tau = tau + np.concatenate([Fb, np.cross(np.asarray(ext[1], dtype=float), Fb)])
        Dv = self.d_lin * nu_r
        rhs = (tau + self.fin_forces(nu_r) + self.drag(nu_r)
               - coriolis(MRB, nu) @ nu
               - coriolis(self.MA, nu_r) @ nu_r
               - Dv
               - self.restoring(eta, W, B, rg, rb)
               + self.MA @ nudot_c)
        nudot = np.linalg.solve(MRB + self.MA, rhs)

        etadot = np.concatenate([R @ nu[:3], t_theta(eta[3], eta[4]) @ nu[3:]])
        Vdot = np.zeros(2)
        for k, V in enumerate((V1, V2)):
            c = tank_cmd[k]
            if (c > 0 and V < p["tank_capacity"]) or (c < 0 and V > 0.0):
                Vdot[k] = p["tank_rate"] * np.sign(c)
        return np.concatenate([etadot, nudot, Vdot]), nudot

    def energy(self, x, dropped=False):
        """Механическая энергия: 1/2 nu^T (M_RB + M_A) nu + потенциал веса и плавучести (проверка V6)."""
        p = self.p
        eta, nu = x[:6], x[6:12]
        m, rg, MRB = self.mass_props(x[12], x[13], dropped)
        R = rot_nb(eta[3], eta[4], eta[5])
        W = m * p["g"]
        B = p["rho"] * p["g"] * self.displaced_volume(dropped)
        z_cg = eta[2] + (R @ rg)[2]
        z_cb = eta[2] + (R @ self.buoyancy_center(dropped))[2]
        T = 0.5 * nu @ (MRB + self.MA) @ nu
        return T - W * z_cg + B * z_cb


def clamp_tanks(x, cap):
    x[12] = min(max(x[12], 0.0), cap)
    x[13] = min(max(x[13], 0.0), cap)
    return x


def rk4_step(veh, x, dt, thr, tank_cmd, vc_n=(0.0, 0.0, 0.0), dropped=False, ext=None):
    """Один шаг Рунге-Кутты 4. Входы (и внешняя сила ext в NED) постоянны на шаге. Тот же алгоритм в GDScript."""
    k1, a1 = veh.deriv(x, thr, tank_cmd, vc_n, dropped, ext)
    k2, _ = veh.deriv(x + 0.5 * dt * k1, thr, tank_cmd, vc_n, dropped, ext)
    k3, _ = veh.deriv(x + 0.5 * dt * k2, thr, tank_cmd, vc_n, dropped, ext)
    k4, _ = veh.deriv(x + dt * k3, thr, tank_cmd, vc_n, dropped, ext)
    xn = x + dt / 6.0 * (k1 + 2 * k2 + 2 * k3 + k4)
    return clamp_tanks(xn, veh.p["tank_capacity"]), a1


def initial_state(depth=0.0, psi=0.0, V1=35e-6, V2=35e-6):
    x = np.zeros(14)
    x[2] = depth
    x[5] = psi
    x[12], x[13] = V1, V2
    return x
