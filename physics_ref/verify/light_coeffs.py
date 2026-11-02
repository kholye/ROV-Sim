"""Коэффициенты воды в каналах камеры и проверка фазовой функции.

  python light_coeffs.py          печать
  python light_coeffs.py --write  записать water_a_rgb, water_bw_rgb, particle_b_shape_rgb в light_params.json

Проверки: (1) β̃ Фурнье-Форанд нормирована (∫ β̃ dΩ = 1) и даёт долю назад phase_ff_bb;
(2) ошибка сведения полосы к одному числу: пропускание exp(−c·L) против спектрального на путях 0,5-10 м.
"""
import json
import sys

import numpy as np

from common import save_results, verdict
from rov import light

p = light.load()
lam, aw = light.pope_fry()
lam_f = np.arange(380, 727.6, 2.5)
w = light.band_weights(lam, p["camera_band_nm"], p["camera_band_sigma_nm"], p["lamp_cct_for_bands"])
L = p["coeff_path_m"]
bw_lam = 0.0022 * (lam / 500.0) ** -4.32
bp_lam = (550.0 / lam) ** 1.0

a_rgb = light.effective_coeff(lam, aw, w, L)
bw_rgb = light.effective_coeff(lam, bw_lam, w, L)
bp_rgb = [float(np.sum(wi * bp_lam) / np.sum(wi)) for wi in w]
print("a_w (R, G, B), 1/м:", np.round(a_rgb, 4))
print("b_w (R, G, B), 1/м:", np.round(bw_rgb, 5))
print("форма b_p (R, G, B):", np.round(bp_rgb, 3))

# (1) фазовая функция
psi = np.concatenate([np.logspace(-4, np.log10(np.pi / 2), 200000), np.linspace(np.pi / 2, np.pi, 200000)[1:]])
f = light.phase_ff(np.cos(psi), p["phase_ff_n"], p["phase_ff_mu"])
g = 2 * np.pi * f * np.sin(psi)
tot = np.trapezoid(g, psi)
back = np.trapezoid(g[psi >= np.pi / 2], psi[psi >= np.pi / 2])
# доля в первых 1e-4 рад (не учтённый край) пренебрежима: f ~ ψ^-μ, интеграл ~ ψ^(2-μ) -> оценка ниже
ok_norm = abs(tot - 1) < 0.02
ok_bb = abs(back - p["phase_ff_bb"]) / p["phase_ff_bb"] < 0.02
print(f"∫β̃ dΩ = {tot:.4f} (ψ от 1e-4 рад), доля назад {back:.5f} против {p['phase_ff_bb']}: "
      f"{verdict(ok_norm and ok_bb)}")

# (2) ошибка одного коэффициента на канал (чистая вода)
paths = np.array([0.5, 1, 2, 3, 5, 10])
err = []
for wi, ai in zip(w, a_rgb):
    spec = np.array([np.sum(wi * np.exp(-aw * x)) / np.sum(wi) for x in paths])
    eff = np.exp(-ai * paths)
    err.append((eff / spec - 1).tolist())
err = np.array(err)
print("ошибка пропускания одного коэффициента, % (строки R, G, B; пути", paths.tolist(), "м):")
print(np.round(100 * err, 2))

save_results("light_coeffs", {"a_rgb": a_rgb, "bw_rgb": bw_rgb, "bp_shape_rgb": bp_rgb, "ff_integral": tot,
                              "ff_backscatter_fraction": back, "ok_norm": bool(ok_norm), "ok_bb": bool(ok_bb),
                              "paths_m": paths.tolist(), "transmission_rel_err": err.tolist()})

if "--write" in sys.argv:
    path = light.PARAMS_PATH
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["water_a_rgb"]["value"] = [round(x, 5) for x in a_rgb]
    raw["water_bw_rgb"]["value"] = [round(x, 6) for x in bw_rgb]
    raw["particle_b_shape_rgb"]["value"] = [round(x, 4) for x in bp_rgb]
    text = "{\n" + ",\n".join(f'  {json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)}'
                              for k, v in raw.items()) + "\n}\n"
    path.write_text(text, encoding="utf-8")
    print("записано в", path)
