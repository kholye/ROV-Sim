"""Показ: нарастание команды движителя (прошивка, 100 % за 3 с) против мгновенной команды.
Ход вперёд 8 с, затем стик вправо (разворот на месте) 6 с (корпус неустойчив по курсу, на долгом ходу уходит с курса). Не проверка, иллюстрация для docs/ui.md."""
import numpy as np

from common import OUT, plt
from rov import params, dynamics as dyn
from rov.control import ThrusterRamp

p = params.load()
veh = dyn.Vehicle(p)
dt = 0.01


def run(ramp):
    x = dyn.initial_state(3.0)
    r = ThrusterRamp(p)
    rows = []
    for i in range(int(16 / dt)):
        t = i * dt
        cmd = np.array([1.0, 1.0]) if t < 8 else np.array([1.0, -1.0]) if t < 14 else np.zeros(2)
        thr = r.step(dt, cmd) if ramp else cmd
        rows.append((t, thr[0], thr[1], x[6], x[11]))
        x, _ = dyn.rk4_step(veh, x, dt, thr, (0, 0))
    return np.array(rows)


a, b = run(True), run(False)
fig, ax = plt.subplots(3, 1, figsize=(9, 8), sharex=True)
ax[0].plot(a[:, 0], a[:, 1], label="левый, с нарастанием"); ax[0].plot(a[:, 0], a[:, 2], label="правый, с нарастанием")
ax[0].plot(b[:, 0], b[:, 1], "--", label="левый, мгновенно"); ax[0].plot(b[:, 0], b[:, 2], "--", label="правый, мгновенно")
ax[0].set(ylabel="команда, доля"); ax[0].legend(fontsize=7, ncol=2)
ax[1].plot(a[:, 0], a[:, 3], label="с нарастанием"); ax[1].plot(b[:, 0], b[:, 3], "--", label="мгновенно")
ax[1].set(ylabel="скорость вперёд, м/с"); ax[1].legend(fontsize=7)
ax[2].plot(a[:, 0], np.degrees(a[:, 4]), label="с нарастанием"); ax[2].plot(b[:, 0], np.degrees(b[:, 4]), "--", label="мгновенно")
ax[2].set(ylabel="скорость рыскания, °/с", xlabel="t, с"); ax[2].legend(fontsize=7)
fig.suptitle("Нарастание команды движителя: 100 % за 3 с (прошивка, Павлов прил. А)")
fig.tight_layout()
fig.savefig(OUT / "thruster_ramp_demo.png")
for name, d in (("с нарастанием", a), ("мгновенно", b)):
    i95 = np.argmax(d[:, 3] >= 0.95 * d[int(7.9 / dt), 3])
    j = np.argmax(np.abs(d[int(8 / dt):, 4]) >= 0.9 * np.abs(d[int(13.9 / dt), 4])) / 100
    print(f"{name}: скорость хода {d[int(7.9/dt),3]:.2f} м/с, 95 % за {d[i95,0]:.1f} с; рыскание макс {np.degrees(np.abs(d[:,4]).max()):.0f} °/с")
