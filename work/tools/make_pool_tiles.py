"""Бесшовная текстура бассейновой плитки (своя, CC0 проекта): 1 × 1 м = 8 × 8 плиток 125 × 125 мм,
шов 3 мм, плитка со скруглённой фаской; цвет плитки слегка гуляет от плитки к плитке, затирка серая.
Пишет godot/assets/textures/pool_tiles/pool_tiles_{diff,nor_gl}_1k.jpg (рельеф OpenGL, Y вверх).
    python make_pool_tiles.py
"""
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "godot" / "assets" / "textures" / "pool_tiles"
N = 1024
TILES = 8
GROUT = 3e-3        # м
BEVEL = 2.5e-3      # м
TILE_RGB = np.array([0.80, 0.90, 0.94])     # sRGB 0..1: светло-голубая глазурь (альбедо ≈0,6-0,8, оценка)
GROUT_RGB = np.array([0.55, 0.56, 0.55])

rng = np.random.default_rng(125)
px = 1.0 / N                                            # м на пиксель
u = (np.arange(N) + 0.5) * px
U, V = np.meshgrid(u, u, indexing="xy")
t = 1.0 / TILES
fu, fv = (U % t), (V % t)
d = np.minimum(np.minimum(fu, t - fu), np.minimum(fv, t - fv))     # до края плитки, м
h = np.clip((d - GROUT / 2) / BEVEL, 0, 1)                           # 0 шов .. 1 плоскость плитки
h = np.sin(h * np.pi / 2)
iu, iv = (U // t).astype(int), (V // t).astype(int)
var = rng.normal(0, 0.025, (TILES, TILES))[iv, iu][..., None]
glaze = TILE_RGB * (1 + var) + 0.01 * rng.normal(0, 1, (N, N, 1))
col = GROUT_RGB * (1 - h[..., None]) + glaze * h[..., None]
OUT.mkdir(parents=True, exist_ok=True)
Image.fromarray(np.clip(col * 255, 0, 255).astype(np.uint8)).save(OUT / "pool_tiles_diff_1k.jpg", quality=92)
# рельеф: высота 1,5 мм у плитки над швом -> нормали (бесшовно: np.roll)
H = 1.5e-3 * h
dx = (np.roll(H, -1, 1) - np.roll(H, 1, 1)) / (2 * px)
dy = (np.roll(H, -1, 0) - np.roll(H, 1, 0)) / (2 * px)
n = np.dstack([-dx, dy, np.ones_like(H)])      # строки изображения идут вниз, ось V текстуры вверх
n /= np.linalg.norm(n, axis=2, keepdims=True)
Image.fromarray(((n * 0.5 + 0.5) * 255).astype(np.uint8)).save(OUT / "pool_tiles_nor_gl_1k.jpg", quality=95)
print("записано", OUT)
