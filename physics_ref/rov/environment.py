"""Течение (Fossen 2011, разд. 8.3) и батарея."""
import numpy as np


def bed_profile(z_above, h):
    """Доля средней по глубине скорости течения на высоте z_above над дном при глубине места h.

    Степенной закон 1/7 (Soulsby 1997, Dynamics of marine sands, гл. 3):
    u(z)/U = (z / (0,32 h))^(1/7) при z < 0,5 h; 1,07 при z >= 0,5 h. Среднее по глубине = 1,00.
    """
    if z_above <= 0.0 or h <= 0.0:
        return 0.0
    if z_above < 0.5 * h:
        return (z_above / (0.32 * h)) ** (1.0 / 7.0)
    return 1.07


class Current:
    """Течение в NED: постоянная часть + Гаусс-Марков первого порядка по скорости.

    V' + V / T = w,  w ~ белый шум с СКО sigma_w; направление фиксировано (горизонтальное).
    В лабораторном бассейне течение нулевое.
    """

    def __init__(self, speed=0.0, direction_rad=0.0, T=0.0, sigma_w=0.0, rng=None):
        self.V0 = speed
        self.dir = direction_rad
        self.T = T
        self.sigma_w = sigma_w
        self.dV = 0.0
        self.rng = rng or np.random.default_rng(0)

    def step(self, dt):
        if self.T > 0.0 and self.sigma_w > 0.0:
            # точная дискретизация процесса Орнштейна-Уленбека
            a = np.exp(-dt / self.T)
            s = self.sigma_w * np.sqrt(self.T / 2.0 * (1 - a * a))
            self.dV = a * self.dV + s * self.rng.standard_normal()
        return self.velocity()

    def velocity(self):
        V = self.V0 + self.dV
        return np.array([V * np.cos(self.dir), V * np.sin(self.dir), 0.0])

    def velocity_at(self, z_above, h):
        """Скорость на высоте z_above над дном (профиль bed_profile); V0 — средняя по глубине."""
        return self.velocity() * bed_profile(z_above, h)


class Battery:
    """Энергия в Дж убывает на P·dt; напряжение: линейная ЭДС по заряду минус I·R."""

    def __init__(self, p):
        self.p = p
        self.E0 = p["battery_energy"] * 3600.0
        self.E = self.E0
        self.used = 0.0

    def power(self, thr, tank_cmd, lamp):
        p = self.p
        P = p["power_hotel"] + p["power_lamp"] * lamp
        P += sum(p["thruster_power_max"] * abs(float(np.clip(s, -1, 1))) ** 3 for s in thr)
        P += sum(p["power_tank_motor"] * (1.0 if c != 0 else 0.0) for c in tank_cmd)
        return P

    def step(self, dt, thr, tank_cmd, lamp=0.0):
        P = self.power(thr, tank_cmd, lamp) if self.E > 0 else 0.0
        dE = min(P * dt, self.E)
        self.E -= dE
        self.used += dE
        return P

    def soc(self):
        return self.E / self.E0

    def voltage(self, P):
        p = self.p
        ocv = p["battery_v_empty"] + (p["battery_v_full"] - p["battery_v_empty"]) * self.soc()
        if self.E <= 0:
            return 0.0
        # I из P = (ocv - I R) I, меньший корень
        R = p["battery_r_int"]
        disc = ocv * ocv - 4 * R * P
        I = (ocv - np.sqrt(max(disc, 0.0))) / (2 * R)
        return ocv - I * R
