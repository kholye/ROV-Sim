"""Размеры и снимки предметов зала со скана LIDAR (данные автора 2026-11-05) для build_lab_room.py.

    blender -b --factory-startup --python blender/scan_measure.py
Читает data/scans/lab_hall_2026-11-05.glb. Пишет blender/lab_room_items.json (только размеры и места; снимков скана модель не использует).
- Приборы на столах: карта высот по точкам скана (ячейка 2 см) над каждым столом; связные области с перепадом
  высоты < 2,5 см — один прибор (коробка по габариту области, высота — медиана). Отбрасываются мелкие (< 0,03 м²),
  низкие (< 8 см) и рыхлые (заполнение < 0,45 — кабели, бумаги).
Шкафы и стенды заданы по разрезам скана (ITEMS ниже).
"""
import json
import math
import os
from collections import deque

import bpy
import numpy as np
from mathutils import Matrix, Vector

ROOT = "D:/Документы/ROV-Sim"
SHIFT = Vector((-0.39, -0.20, 1.50))

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=ROOT + "/data/scans/lab_hall_2026-11-05.glb")
sc = bpy.context.scene
for o in sc.objects:
    if o.parent is None:
        o.location += SHIFT
bpy.context.view_layer.update()

# точки скана: вершины и центры граней
P = []
for o in [o for o in sc.objects if o.type == "MESH"]:
    me = o.data
    M = o.matrix_world
    vs = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", vs)
    pc = np.empty(len(me.polygons) * 3, np.float32)
    me.polygons.foreach_get("center", pc)
    co = np.concatenate([vs.reshape(-1, 3), pc.reshape(-1, 3)])
    co = (np.array(M)[:3, :3] @ co.T).T + np.array(M)[:3, 3]
    P.append(co)
P = np.concatenate(P)
print("SCAN точек", len(P), flush=True)

# столы: (имя, начало у стены, вдоль, в зал, длина, глубина, высота столешницы) — по разрезам скана
TABLES = {
    "N": ((-2.53, 2.775), (1.0, 0.004), (0.0, -1.0), 4.81, 0.68, 1.03),
    "W": ((-2.95, 2.05), (0.0, -1.0), (1.0, 0.0), 4.03, 0.70, 1.03),
    "S": ((2.88, -2.735), (-1.0, -0.031), (0.031, 1.0), 3.33, 0.66, 1.04),
    "E": ((2.67, 2.96), (0.305, -0.952), (-0.952, -0.305), 5.2, 0.72, 1.03),
    "Z": ((-3.91, -0.39), (0.0, -1.0), (1.0, 0.0), 1.29, 0.78, 1.06),
}
R = 0.02
devices = []
for tn, (o, dv, nv, L, D, top) in TABLES.items():
    o, dv, nv = np.array(o), np.array(dv) / np.linalg.norm(dv), np.array(nv) / np.linalg.norm(nv)
    rel = P[:, :2] - o
    a, b = rel @ dv, rel @ nv
    s = (a > 0) & (a < L) & (b > 0.04) & (b < D) & (P[:, 2] > top + 0.02) & (P[:, 2] < 1.95)
    na, nb = int(L / R) + 1, int(D / R) + 1
    H = np.full((na, nb), np.nan)
    for i, j, v in zip((a[s] / R).astype(int), (b[s] / R).astype(int), P[s, 2]):
        if np.isnan(H[i, j]) or v > H[i, j]:
            H[i, j] = v
    seen = np.zeros_like(H, bool)
    for i in range(na):
        for j in range(nb):
            if seen[i, j] or np.isnan(H[i, j]):
                continue
            q, cells = deque([(i, j)]), []
            seen[i, j] = True
            while q:
                ci, cj = q.popleft()
                cells.append((ci, cj))
                for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ni, nj = ci + di, cj + dj
                    if 0 <= ni < na and 0 <= nj < nb and not seen[ni, nj] and not np.isnan(H[ni, nj]) \
                            and abs(H[ni, nj] - H[ci, cj]) < 0.025:
                        seen[ni, nj] = True
                        q.append((ni, nj))
            cs = np.array(cells)
            a0, a1 = cs[:, 0].min() * R, (cs[:, 0].max() + 1) * R
            b0, b1 = cs[:, 1].min() * R, (cs[:, 1].max() + 1) * R
            area = len(cells) * R * R
            h = float(np.median([H[c] for c in cells])) - top
            if area < 0.03 or h < 0.08 or area / ((a1 - a0) * (b1 - b0)) < 0.45:
                continue
            devices.append(dict(name=f"Dev_{tn}{len(devices)}", table=tn, o=o.tolist(), dv=dv.tolist(), nv=nv.tolist(),
                                a=[a0, a1], b=[b0, b1], z=[top, top + h]))
print("SCAN приборов", len(devices), flush=True)

# шкафы и стенды (по разрезам и развёрткам скана): центр низа лицевой стороны, нормаль в зал, ширина, глубина, высота
ITEMS = [
    dict(name="Cab_SE_wardrobe", kind="cabinet", c=(3.40, -2.72, 0.30), n=(0, 1), w=0.76, d=0.19, h=2.10),   # в нише
    dict(name="Cab_S_glass", kind="cabinet", c=(-1.545, -2.90, 0.30), n=(0, 1), w=0.95, d=0.37, h=1.59),
    dict(name="Cab_SW_grey", kind="cabinet", c=(-3.685, -2.77, 0.30), n=(0, 1), w=0.76, d=0.26, h=1.75),
    dict(name="Cab_WZ_books", kind="cabinet", c=(-4.87, -1.09, 0.30), n=(1, 0), w=1.16, d=0.38, h=1.90),
    dict(name="Board_S1", kind="board", c=(1.70, -2.79, 1.75), n=(0, 1), w=1.00, d=0.02, h=0.70),
    dict(name="Board_S2", kind="board", c=(0.00, -2.82, 1.65), n=(0, 1), w=1.00, d=0.02, h=0.75),
    dict(name="Board_S3", kind="board", c=(-1.54, -3.28, 2.00), n=(0, 1), w=0.92, d=0.02, h=0.55),
    dict(name="Board_S4", kind="board", c=(-2.43, -2.90, 1.98), n=(0, 1), w=0.70, d=0.02, h=0.57),
    dict(name="Board_WB", kind="board", c=(-4.475, -3.02, 1.68), n=(0, 1), w=0.35, d=0.02, h=0.50),
]
NE, DV = np.array([2.67, 2.96]), np.array([0.305, -0.952])
NV = np.array([-0.952, -0.305])
for k, (u0, u1) in enumerate([(2.22, 3.19), (0.92, 1.89)]):          # стенды на восточной стене (по развёртке)
    p = NE + DV * (u0 + u1) / 2 + NV * 0.02
    ITEMS.append(dict(name=f"Board_E{k + 1}", kind="board", c=(float(p[0]), float(p[1]), 1.85), n=NV.tolist(), w=u1 - u0, d=0.02, h=0.63))

json.dump(dict(devices=devices, items=ITEMS, tables=TABLES), open(ROOT + "/blender/lab_room_items.json", "w", encoding="utf-8"),
          indent=1, ensure_ascii=False)
print("SCAN предметов", len(ITEMS), flush=True)
