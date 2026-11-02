"""V3(а), чувствительность к реализации шума датчика: те же ПИД и сценарий, что в v3_pid.py
(полная модель 6 ст. св., 300 с, старт с 0,2 м), 10 реализаций шума на каждую цель.
Критерий не меняется (max отклонение за последние 100 с не больше удвоенного из т. 9);
скрипт показывает, насколько вердикт v3_pid.py (одна реализация, seed = 3) зависит от случая.
"""
import numpy as np

from common import save_results
from rov import params
from rov.sim import run_depth_hold

p = params.load()
KP, KI, KD = 0.2, 0.0, 5.1
measured = {0.5: 0.05, 1.5: 0.02, 2.0: 0.027}
res = {"pid": [KP, KI, KD], "seeds": list(range(1, 11))}
for target, meas in measured.items():
    devs = []
    for seed in res["seeds"]:
        out = run_depth_hold(p, target, KP, KI, KD, 300.0, 0.02, 0.2, depth_noise=p["depth_noise_sigma"], seed=seed)
        z = out[out[:, 0] >= 200.0, 1]
        devs.append(float(np.abs(z - target).max()))
    devs = np.array(devs)
    res[str(target)] = {"criterion_m": 2 * meas, "median_m": float(np.median(devs)), "min_m": float(devs.min()),
                        "max_m": float(devs.max()), "share_within": float(np.mean(devs <= 2 * meas)),
                        "all_m": devs.round(4).tolist()}
    print(target, res[str(target)], flush=True)
save_results("v3_seeds", res)
