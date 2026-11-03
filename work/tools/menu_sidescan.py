"""Палитра «медь» для снимка бокового обзора в меню и обрезка контурного рисунка аппарата.

  physics_ref/.venv/Scripts/python work/tools/menu_sidescan.py <relief.png> <lineart.png>
  -> godot/assets/ui/menu_sidescan.jpg, godot/assets/ui/rov_lineart.png

relief.png и lineart.png делает blender/render_menu_art.py. Зерно (шум 0,06) — только вид, как у записи прибора.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
COPPER = [(0.0, (8, 5, 2)), (0.35, (70, 38, 12)), (0.7, (190, 120, 45)), (1.0, (255, 226, 160))]

relief, lineart = sys.argv[1], sys.argv[2]
g = np.asarray(Image.open(relief).convert("L"), dtype=float) / 255.0
g = (g - g.min()) / (g.max() - g.min() + 1e-9)
g = np.clip(g + np.random.default_rng(1).normal(0, 0.06, g.shape), 0, 1) ** 1.3
xs = [s[0] for s in COPPER]
out = np.stack([np.interp(g, xs, [s[1][c] for s in COPPER]) for c in range(3)], axis=-1)
Image.fromarray(out.astype(np.uint8)).save(ROOT / "godot/assets/ui/menu_sidescan.jpg", quality=88)
im = Image.open(lineart)
im.crop(im.getbbox()).save(ROOT / "godot/assets/ui/rov_lineart.png", optimize=True)
print("ok")
