"""Бортовое управление как на пульте и у Дунаева.

- микширование правого стика пульта (протокол пульта на MATLAB);
- ПИД глубины с коэффициентами на сетке пульта 0,0-9,9 шаг 0,1 (как в пульте);
- поршни «вкл/выкл» по порогу 0,005 (Дунаев 2.4, прил. А), период 0,1 с.
"""
import numpy as np


def joystick_to_motors(x, y, dead=15000):
    """Правый стик (-32768..32767) -> (левый, правый) в -100..100."""
    def norm(a):
        if abs(a) < dead:
            return 0.0
        v = (a - dead * np.sign(a)) / (32768 - dead)
        return float(np.clip(v, -1.0, 1.0))
    xn, yn = norm(x), norm(y)
    L, R = yn + xn, yn - xn
    mx = max(abs(L), abs(R))
    if mx > 1:
        L, R = L / mx, R / mx
    return int(round(100 * L)), int(round(100 * R))


class ThrusterRamp:
    """Нарастание команды движителя, как в прошивке (Павлов, прил. А, speedControl).

    Команда s ∈ [-1, 1] приближается к заданной линейно: полный ход за thruster_ramp_time (3 с),
    в обе стороны, через ноль тоже (от +1 до -1 за 6 с).
    """

    def __init__(self, p):
        self.rate = 1.0 / p["thruster_ramp_time"]
        self.s = np.zeros(2)

    def step(self, dt, target):
        d = np.asarray(target, float) - self.s
        lim = self.rate * dt
        self.s = self.s + np.clip(d, -lim, lim)
        return self.s.copy()

    def reset(self):
        self.s = np.zeros(2)


def quantize_gain(k):
    """Коэффициент так, как его передаёт пульт v7: целое 0..99 = k*10 (сетка 0,1)."""
    # пульт не округляет (ввод должен быть кратен 0,1); здесь округление половины вверх
    return min(max(int(np.floor(k * 10 + 0.5)), 0), 99) / 10.0


class DepthPID:
    """ПИД глубины. e = H - h (м, глубина вниз). Выход > порога: набирать воду в обе цистерны.

    Структура (порядок, интеграл с ограничением, производная по ошибке) по коду Дунаева прил. А.
    predict_T > 0 включает прогноз глубины Дунаева (ф. 12); в прошивке не известно, был ли он.
    """

    def __init__(self, kp, ki, kd, p, predict_T=0.0):
        self.kp, self.ki, self.kd = quantize_gain(kp), quantize_gain(ki), quantize_gain(kd)
        self.thr = p["pid_threshold"]
        self.ilim = p["pid_integral_limit"]
        self.dt = p["control_period"]
        self.T = predict_T
        self.integral = 0.0
        self.prev = None
        self.prev_h = None
        self.prev_v = 0.0

    def update(self, target, h):
        v = 0.0 if self.prev_h is None else (h - self.prev_h) / self.dt
        a = (v - self.prev_v) / self.dt
        self.prev_h, self.prev_v = h, v
        h_eff = h + v * self.T + a * self.T ** 2 / 2 if self.T > 0 else h
        e = target - h_eff
        self.integral = float(np.clip(self.integral + e * self.dt, -self.ilim, self.ilim))
        de = 0.0 if self.prev is None else (e - self.prev) / self.dt
        self.prev = e
        u = self.kp * e + self.ki * self.integral + self.kd * de
        if u > self.thr:
            return 1      # набрать воду: тяжелее, глубже
        if u < -self.thr:
            return -1     # вытеснить воду
        return 0
