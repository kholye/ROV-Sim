"""V5, порт: шейдер Godot против эталона light.py на тех же лучах.

Godot (окно нужно для рендера) пишет пиксели центров секторов:
  Godot --path godot res://tests/light_render_test.tscn -- --out docs/verification/v5_godot_render.json
Здесь те же лучи считаются эталоном (2000 шагов интеграла против 16 в шейдере), экспозиция та же,
кодирование sRGB. Критерий: расхождение не больше 3 единиц из 255 в каждом канале (шаг интеграла,
32-битная арифметика GPU, округление). Заодно проверяется, что вывод Godot переводит линейный цвет в sRGB.
"""
import json
import sys

import numpy as np

from common import OUT, save_results, verdict
from rov import light

p = light.load()
src = OUT / "v5_godot_render.json" if len(sys.argv) < 2 else sys.argv[1]
data = json.loads(open(src, encoding="utf-8").read())
res = {"cases": []}
worst = 0.0
worst_lin = 0.0
for cs in data["cases"]:
    bp = p[cs["water"] + "_bp550"]
    w = light.Water(p, b_p550=bp)
    lamp = light.Lamp(cs["lamp_pos"], cs["lamp_dir"], 1.0, cs["lamp_i"])
    cam = np.array(cs["cam"], float)
    P = np.array([s["point"] for s in cs["sectors"]], float)
    alb = np.array(p["plate_albedo_rgb"], float)
    v = P - cam
    D = np.linalg.norm(v, axis=1)
    dirs = v / D[:, None]
    N = np.array([s["normal"] for s in cs["sectors"]], float)
    L = light.radiance(cam, dirs, D, N, alb, lamp, w, E_surf=cs["esurf"], up=(0, 1, 0),
                       depth_of=lambda X: np.maximum(0.0 - X[..., 1], 0.0), n=2000)
    ref = np.round(255 * light.srgb_encode(cs["exposure"] * L))
    ref_lin = np.round(255 * np.clip(cs["exposure"] * L, 0, 1))
    got = np.array([s["rgb8"] for s in cs["sectors"]], float)
    err = float(np.max(np.abs(got - ref)))
    err_lin = float(np.max(np.abs(got - ref_lin)))
    worst = max(worst, err)
    worst_lin = max(worst_lin, err_lin)
    res["cases"].append({"name": cs["name"], "max_err_srgb": err, "max_err_if_linear_output": err_lin,
                         "godot": got.tolist(), "reference": ref.tolist()})
    print(f"  {cs['name']:20s} макс. расхождение {err:.0f}/255 (если бы вывод был линейным: {err_lin:.0f})"
          f"  пример: Godot {got[9].astype(int).tolist()} эталон {ref[9].astype(int).tolist()}")
ok = worst <= 3
res["ok"] = bool(ok)
res["worst"] = worst
print(f"Шейдер = эталон (≤ 3/255): {verdict(ok)}; худшее {worst:.0f}/255")
save_results("v5_godot", res)
