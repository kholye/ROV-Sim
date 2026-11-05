"""Зал над лабораторным бассейном кафедры — модель по скану LIDAR (iPhone, данные автора 2026-11-05).

    blender -b --factory-startup --python blender/build_lab_room.py
Пишет blender/lab_room.blend. Сам скан в модель не входит: по нему сняты размеры (точки скана —
data/scans/lab_hall_2026-11-05.glb; размеры предметов — blender/scan_measure.py), всё построено заново.
Оси: X восток, Y север, Z вверх (как build_lab_pool.py); вода Z = 0; перевод скана (x − 0,39; y − 0,20; z + 1,50).

Размеры (м; точность скана iPhone ~1-2 см, отсчёт по разрезам ~2 см):
- пол Z = 0,30, потолок 2,72 (высота зала 2,42); балки под потолком низом на 2,52: вдоль X (Y 0,23…0,40),
  вдоль Y (X 2,08…2,35) и на границе западной части (X −2,95…−2,62);
- контур стен — WALLS ниже (по разрезу на высоте 1,75-2,35 м); окна: два в северной стене (X −2,43…−1,43 и
  0,47…1,50, Z 1,07…2,50, рамы в нишах 0,26 и 0,18 м), одно в северной стене западной части, одно на скосе юго-востока;
- светильники: 6 в зале (2 ряда × 3, 1,25 м вдоль X), 3 у восточной стены, 2 в западной части — центры по скану;
- пол над бассейном — 4 × 4 щита на раме (швы по скану), открыт щит аппарата; люки гидроакустики закрыты.
Не измерено (оценка): толщина стен (0,3 м), вид за окнами, коридор за западной дверью, глубина ниш у пола.
Цвета — по скану, яркость выровнена (свет в скане запечён): охра севера и запада, светло-серый юга и востока.
"""
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

ROOT = "D:/Документы/ROV-Sim"
TEX = ROOT + "/godot/assets/textures"
FZ, CZ = 0.30, 2.72                     # пол, потолок
BEAM_Z = 2.52
WT = 0.30                               # толщина стен (оценка)

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
coll = sc.collection


def srgb(c):
    return tuple(((v / 255) ** 2.2) for v in c)


# ---------------- материалы
def pbr(name, tex, tint=(255, 255, 255), scale=1.0, rough=None, bump=1.0, metal=0.0):
    """PBR по набору Poly Haven, цвет умножен на tint (sRGB 0-255); scale — метров на повтор (для UV)."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m["uv_m"] = scale
    nt = m.node_tree
    b = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Metallic"].default_value = metal
    d = f"{TEX}/{tex}/{tex}_"
    di = nt.nodes.new("ShaderNodeTexImage")
    di.image = bpy.data.images.load(d + "diff_1k.jpg", check_existing=True)
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs[0].default_value = 1.0
    mul.inputs[7].default_value = (*srgb(tint), 1)
    nt.links.new(di.outputs["Color"], mul.inputs[6])
    nt.links.new(mul.outputs[2], b.inputs["Base Color"])
    if os.path.exists(d + "rough_1k.jpg") and rough is None:
        ri = nt.nodes.new("ShaderNodeTexImage")
        ri.image = bpy.data.images.load(d + "rough_1k.jpg", check_existing=True)
        ri.image.colorspace_settings.name = "Non-Color"
        nt.links.new(ri.outputs["Color"], b.inputs["Roughness"])
    else:
        b.inputs["Roughness"].default_value = rough if rough is not None else 0.8
    if os.path.exists(d + "nor_gl_1k.jpg"):
        ni = nt.nodes.new("ShaderNodeTexImage")
        ni.image = bpy.data.images.load(d + "nor_gl_1k.jpg", check_existing=True)
        ni.image.colorspace_settings.name = "Non-Color"
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.inputs["Strength"].default_value = bump
        nt.links.new(ni.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    return m


def flat(name, col, rough=0.6, metal=0.0, emit=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m["uv_m"] = 1.0
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*srgb(col), 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if emit:
        b.inputs["Emission Color"].default_value = (*srgb(col), 1)
        b.inputs["Emission Strength"].default_value = emit
    return m


M_WALL_Y = pbr("ROOM_wall_ochre", "painted_plaster_wall", (236, 196, 120), 2.0, bump=0.6)
M_WALL_G = pbr("ROOM_wall_grey", "painted_plaster_wall", (214, 218, 214), 2.0, bump=0.6)
M_CEIL = pbr("ROOM_ceiling", "painted_plaster_wall", (246, 243, 236), 2.5, bump=0.8)
M_PLANK = pbr("ROOM_floor_red", "distressed_painted_planks", (255, 120, 90), 1.2, bump=0.7)
M_TILE = pbr("ROOM_floor_tile", "floor_tiles_08", (235, 205, 175), 0.8, bump=0.6)
M_PARQ = pbr("ROOM_floor_parquet", "herringbone_parquet", (230, 200, 170), 1.0)
M_CONC = pbr("ROOM_floor_concrete", "concrete_floor_worn_001", (200, 192, 175), 2.0)
M_MAT = flat("ROOM_floor_mat", (58, 58, 55), 0.75)          # гладкая резина (по данным автора — резиновые коврики)
M_STEEL = flat("ROOM_steel", (95, 92, 86), 0.5, 1.0)
M_BEAMW = flat("ROOM_wet_beam", (40, 28, 20), 0.7)
M_FRAME = flat("ROOM_window_frame", (205, 205, 198), 0.5)
M_SKY = flat("ROOM_window_sky", (170, 200, 235), 0.2, emit=2.5)        # дневной свет за окном (оценка)
M_SILL = flat("ROOM_sill", (215, 212, 205), 0.4)
M_LAMP = flat("ROOM_lamp_body", (225, 225, 222), 0.4, 0.3)
M_TUBE = flat("ROOM_lamp_tube", (255, 250, 238), 0.2, emit=18.0)      # ЛБ-40 (оценка яркости)
M_HATCH_W = pbr("ROOM_hatch_wood", "distressed_painted_planks", (150, 110, 80), 0.6)
M_HATCH_B = flat("ROOM_hatch_blue", (45, 105, 165), 0.45, 0.6)
M_DARK = flat("ROOM_corridor", (40, 38, 35), 0.9)
M_CONDUIT = flat("ROOM_conduit", (200, 200, 195), 0.5)


# ---------------- геометрия
def obj_from_bm(name, bm, mat):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    coll.objects.link(o)
    me.materials.append(mat)
    return o


def box_uv(o):
    """UV проекцией по главной оси нормали, масштаб — uv_m материала (метров на повтор)."""
    me = o.data
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    uv = me.uv_layers.active.data
    M = o.matrix_world
    for p in me.polygons:
        s = me.materials[p.material_index].get("uv_m", 1.0) if me.materials else 1.0
        n = (M.to_3x3() @ p.normal)
        ax = max(range(3), key=lambda i: abs(n[i]))
        for li in p.loop_indices:
            c = M @ me.vertices[me.loops[li].vertex_index].co
            u, v = [(c.y, c.z), (c.x, c.z), (c.x, c.y)][ax]
            uv[li].uv = (u / s, v / s)


def box(name, lo, hi, mat):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector([lo[i] + (v.co[i] + 0.5) * (hi[i] - lo[i]) for i in range(3)])
    o = obj_from_bm(name, bm, mat)
    box_uv(o)
    return o


def prism(name, poly, z0, z1, mat):
    """Призма по многоугольнику в плане."""
    bm = bmesh.new()
    lo = [bm.verts.new((x, y, z0)) for x, y in poly]
    hi = [bm.verts.new((x, y, z1)) for x, y in poly]
    bm.faces.new(lo[::-1])
    bm.faces.new(hi)
    n = len(poly)
    for i in range(n):
        bm.faces.new([lo[i], lo[(i + 1) % n], hi[(i + 1) % n], hi[i]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = obj_from_bm(name, bm, mat)
    box_uv(o)
    return o


def cut(o, cutter_lo, cutter_hi):
    c = box("_cut", cutter_lo, cutter_hi, M_DARK)
    m = o.modifiers.new("cut", "BOOLEAN")
    m.operation = "DIFFERENCE"
    m.object = c
    m.solver = "EXACT"
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.modifier_apply(modifier="cut")
    bpy.data.objects.remove(c)
    box_uv(o)


# контур стен (внутренняя грань, по часовой стрелке), материал стены
WALLS = [
    ((-3.00, 2.775), (0.45, 2.79), M_WALL_Y),     # север, запад от окна 2 (окно 1 в нём)
    ((0.45, 2.79), (0.45, 2.95), M_WALL_Y),       # уступ
    ((0.45, 2.95), (2.67, 2.96), M_WALL_Y),       # север, восток (окно 2)
    ((2.67, 2.96), (4.38, -2.38), M_WALL_G),      # восток, скошенная
    ((4.38, -2.38), (4.10, -2.70), M_WALL_G),     # скос юго-востока (окно 3)
    ((4.10, -2.70), (-1.05, -2.88), M_WALL_G),    # юг
    ((-1.05, -2.88), (-2.03, -2.92), M_WALL_G),   # юг, ниша двери со шкафом
    ((-2.03, -2.92), (-2.95, -2.94), M_WALL_G),
    ((-2.95, -2.94), (-2.95, -3.00), M_WALL_G),
    ((-2.95, -3.00), (-5.25, -3.05), M_WALL_G),   # юг западной части
    ((-5.25, -3.05), (-5.25, -0.55), M_WALL_G),   # запад западной части (дверь в коридор)
    ((-5.25, -0.55), (-4.62, -0.50), M_WALL_G),
    ((-4.62, -0.50), (-4.62, 1.12), M_WALL_G),
    ((-4.62, 1.12), (-3.00, 1.12), M_WALL_G),     # север западной части (окно 0)
    ((-3.00, 1.12), (-3.00, 2.775), M_WALL_Y),    # запад зала
]
OUTLINE = [w[0] for w in WALLS]


def inside(p):
    x, y = p
    c = False
    for (x1, y1), (x2, y2) in zip(OUTLINE, OUTLINE[1:] + OUTLINE[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


# стены — один массив: прямоугольник с запасом минус зал по контуру (у тонких уступов нет торчащих торцов)
xs_, ys_ = [p[0] for p in OUTLINE], [p[1] for p in OUTLINE]
ring = box("Walls", (min(xs_) - 1.0, min(ys_) - 1.0, FZ - 0.02), (max(xs_) + 1.0, max(ys_) + 1.0, CZ + 0.02), M_WALL_G)
ring.data.materials.append(M_WALL_Y)
hole = prism("_hole", OUTLINE, FZ - 0.5, CZ + 0.5, M_DARK)
mod = ring.modifiers.new("hole", "BOOLEAN")
mod.operation, mod.object, mod.solver = "DIFFERENCE", hole, "EXACT"
bpy.context.view_layer.objects.active = ring
bpy.ops.object.modifier_apply(modifier="hole")
bpy.data.objects.remove(hole)


def cut_rot(o, c, size, ang):
    """Вырез повёрнутым на ang (вокруг Z) прямоугольником с центром c и размерами size."""
    cb = box("_cutr", [-v / 2 for v in size], [v / 2 for v in size], M_DARK)
    cb.location, cb.rotation_euler = c, (0, 0, ang)
    m = o.modifiers.new("cut", "BOOLEAN")
    m.operation, m.object, m.solver = "DIFFERENCE", cb, "EXACT"
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.modifier_apply(modifier="cut")
    bpy.data.objects.remove(cb)


# окна: проём, рама в нише, стекло — дневной свет
WINDOWS = [   # (имя, x0, x1, y стены, y рамы, z0, z1, импосты X, ригели Z)
    ("W1", -2.43, -1.43, 2.775, 3.04, 1.07, 2.50, [-1.91], [1.58, 2.05]),
    ("W2", 0.47, 1.50, 2.95, 3.13, 1.07, 2.50, [0.95], [1.58, 2.05]),
    ("W0", -4.45, -3.85, 1.12, 1.30, 1.07, 2.50, [-4.15], [1.58, 2.05]),
]
for nm, x0, x1, yw, yf, z0, z1, mull, trans in WINDOWS:
    cut(ring, (x0, yw - 0.05, z0), (x1, yw + 1.5, z1))
    t = 0.05
    box(f"{nm}_frameL", (x0, yf, z0), (x0 + t, yf + 0.06, z1), M_FRAME)
    box(f"{nm}_frameR", (x1 - t, yf, z0), (x1, yf + 0.06, z1), M_FRAME)
    box(f"{nm}_frameB", (x0, yf, z0), (x1, yf + 0.06, z0 + t), M_FRAME)
    box(f"{nm}_frameT", (x0, yf, z1 - t), (x1, yf + 0.06, z1), M_FRAME)
    for xm in mull:
        box(f"{nm}_mull", (xm - 0.03, yf, z0), (xm + 0.03, yf + 0.06, z1), M_FRAME)
    for zt in trans:
        box(f"{nm}_trans", (x0, yf, zt - 0.025), (x1, yf + 0.06, zt + 0.025), M_FRAME)
    box(f"{nm}_sky", (x0, yf + 0.08, z0), (x1, yf + 0.09, z1), M_SKY)
    box(f"{nm}_sill", (x0 - 0.04, yw - 0.06, z0 - 0.04), (x1 + 0.04, yf, z0), M_SILL)
# вентилятор в нижней левой створке окна 2 (по скану)
bpy.ops.mesh.primitive_cylinder_add(radius=0.12, depth=0.04, location=(0.70, 3.10, 1.80), rotation=(math.pi / 2, 0, 0))
fan = bpy.context.active_object
fan.name = "W2_fan"
fan.data.materials.append(M_LAMP)
# окно 3 — на скосе юго-востока (X 4,05…4,35, Z 1,55…2,60 по развёртке южной стены; ниша 0,2 м — оценка)
sw = Vector((4.10 - 4.38, -2.70 + 2.38))
ang3 = math.atan2(sw.y, sw.x)
n3 = Vector((-sw.y, sw.x)).normalized()
c3 = Vector((4.24, -2.54))
if inside(c3 + n3 * 0.05):
    n3 = -n3                                          # наружу
cut_rot(ring, (c3.x + n3.x * 0.5, c3.y + n3.y * 0.5, 2.075), (sw.length * 0.75, 1.05, 1.05), ang3)
bpy.ops.mesh.primitive_plane_add(size=1, location=(c3.x + n3.x * 0.25, c3.y + n3.y * 0.25, 2.075))
p3 = bpy.context.active_object
p3.name = "W3_sky"
p3.scale = (sw.length * 0.75, 1.05, 1)
p3.rotation_euler = (math.pi / 2, 0, ang3)
p3.data.materials.append(M_SKY)
# ниша двери со шкафом на юге (X −2,03…−1,07, до Y −3,30, высота до 2,55) и дверь в коридор на западе (Y −2,85…−2,10)
cut(ring, (-2.03, -3.30, FZ - 0.05), (-1.07, -2.80, 2.55))
cut(ring, (-5.60, -2.85, FZ - 0.05), (-5.10, -2.10, 2.35))
box("CorridorDark", (-6.2, -2.95, FZ), (-5.55, -2.0, 2.4), M_DARK)
# ниша у юго-востока (X 3,15…3,87, до Y −2,91; за шкафом, высота — оценка)
cut(ring, (3.15, -2.91, FZ - 0.05), (3.87, -2.65, 2.35))
# цвет стен по ближайшему отрезку контура (охра — север и запад зала)
def seg_dist(p, a, b):
    a, b = Vector(a), Vector(b)
    t = max(0.0, min(1.0, (p - a).dot(b - a) / max((b - a).length_squared, 1e-9)))
    return (a + (b - a) * t - p).length


for f in ring.data.polygons:
    c = f.center.xy
    k = min(range(len(WALLS)), key=lambda i: seg_dist(c, WALLS[i][0], WALLS[i][1]))
    f.material_index = 1 if WALLS[k][2] is M_WALL_Y else 0
box_uv(ring)

# пол: вне щитов — плитка (зал), паркет и бетон (западная часть)
prism("FloorTile", [(-3.0, 2.78), (2.67, 2.96), (4.38, -2.38), (4.10, -2.70), (-3.0, -2.95)], FZ - 0.05, FZ - 0.001, M_TILE)
cut(bpy.data.objects["FloorTile"], (-2.19, -2.07, FZ - 0.1), (2.18, 2.07, FZ + 0.1))   # под щитами — бассейн
prism("FloorParquet", [(-4.62, 1.12), (-3.0, 1.12), (-3.0, -1.70), (-4.62, -1.70)], FZ - 0.05, FZ - 0.001, M_PARQ)
prism("FloorConcrete", [(-5.25, -1.70), (-3.0, -1.70), (-3.0, -3.05), (-5.25, -3.05)], FZ - 0.05, FZ - 0.001, M_CONC)
prism("FloorConcreteW", [(-5.25, -0.55), (-4.62, -0.50), (-4.62, -1.70), (-5.25, -1.70)], FZ - 0.05, FZ - 0.001, M_CONC)
# резиновые коврики (по скану)
for k, (xa, xb, ya, yb) in enumerate([(-2.22, -1.51, -0.75, 0.66), (-2.26, -2.01, 0.85, 1.75), (-2.00, -1.55, -2.10, -0.75),
                                       (0.10, 1.08, 0.55, 1.28), (2.18, 2.62, 0.10, 1.85)]):
    box(f"Mat_{k}", (xa, ya, FZ), (xb, yb, FZ + 0.006), M_MAT)

# потолок и балки
prism("Ceiling", OUTLINE, CZ, CZ + 0.05, M_CEIL)
box("BeamX", (-2.95, 0.23, BEAM_Z), (2.08, 0.40, CZ), M_CEIL)
box("BeamY", (2.08, -2.78, BEAM_Z), (2.35, 2.96, CZ), M_CEIL)
box("BeamW", (-2.95, -3.0, BEAM_Z), (-2.62, 2.775, CZ), M_CEIL)
box("PilasterSE", (2.22, -2.78, FZ), (2.38, -2.50, BEAM_Z), M_WALL_G)
box("PilasterSW", (-3.00, -2.94, FZ), (-2.80, -2.70, BEAM_Z), M_WALL_G)

# светильники: корпус 1,25 × 0,14 × 0,06 м, две трубки снизу (ЛПО 2×40, оценка)
LAMPS = [(x, y, 0.0) for y in (1.48, -1.35) for x in (1.17, -0.29, -1.74)]
ew = math.atan2(-5.34, 1.71)                          # вдоль восточной стены
LAMPS += [(2.82, 1.82, ew), (3.00, 0.00, ew), (3.37, -1.81, ew), (-4.17, -0.03, math.pi / 2), (-4.17, -1.80, math.pi / 2)]
for k, (x, y, a) in enumerate(LAMPS):
    body = box(f"Lamp_{k}", (-0.625, -0.07, CZ - 0.06), (0.625, 0.07, CZ), M_LAMP)
    t1 = box(f"LampTube_{k}a", (-0.60, -0.045, CZ - 0.075), (0.60, -0.02, CZ - 0.05), M_TUBE)
    t2 = box(f"LampTube_{k}b", (-0.60, 0.02, CZ - 0.075), (0.60, 0.045, CZ - 0.05), M_TUBE)
    for o in (body, t1, t2):
        o.rotation_euler = (0, 0, a)
        o.location = (x, y, 0)
# кабельные короба под потолком вдоль стен зала (по развёрткам: Z ≈ 2,62)
for k, ((x1, y1), (x2, y2), _) in enumerate(WALLS[:6]):
    d = Vector((x2 - x1, y2 - y1))
    if d.length < 0.5:
        continue
    nrm = Vector((-d.y, d.x)).normalized()
    mid = Vector(((x1 + x2) / 2, (y1 + y2) / 2))
    if not inside(mid + nrm * 0.02):
        nrm = -nrm
    o = box(f"Conduit_{k}", (-d.length / 2, -0.015, 2.60), (d.length / 2, 0.015, 2.63), M_CONDUIT)
    o.rotation_euler = (0, 0, math.atan2(d.y, d.x))
    o.location = (mid.x + nrm.x * 0.02, mid.y + nrm.y * 0.02, 0)

# ---------------- пол над бассейном (щиты на раме, швы по скану)
XS = [-2.17, -1.09, 0.01, 1.08, 2.16]
YS = [2.05, 1.03, -0.02, -1.03, -2.05]
OPEN = (1, 1)
g = 0.02
for i in range(4):
    for j in range(4):
        xa, xb, ya, yb = XS[i] + g, XS[i + 1] - g, YS[j + 1] + g, YS[j] - g
        if (i, j) == OPEN:
            continue
        box(f"Plate_{i}{j}", (xa, ya, FZ - 0.03), (xb, yb, FZ), M_PLANK)
for k, x in enumerate(XS):
    box(f"BarX_{k}", (x - g, YS[-1] - g, FZ - 0.05), (x + g, YS[0] + g, FZ - 0.001), M_STEEL)
    box(f"JoistX_{k}", (x - 0.05, YS[-1], FZ - 0.20), (x + 0.05, YS[0], FZ - 0.05), M_BEAMW)
for k, y in enumerate(YS):
    box(f"BarY_{k}", (XS[0] - g, y - g, FZ - 0.05), (XS[-1] + g, y + g, FZ - 0.001), M_STEEL)
    box(f"JoistY_{k}", (XS[0], y - 0.05, FZ - 0.202), (XS[-1], y + 0.05, FZ - 0.052), M_BEAMW)
# снятый щит лежит плашмя на соседнем щите с запада (где лежал — оценка)
box("PlateLoose", (-2.13, 0.04, FZ + 0.006), (-1.11, 0.99, FZ + 0.036), M_PLANK)
# борт бассейна над водой (бетон, Z 0…0,25 — от воды до низа балок) и уступ под щитами до края пола (оценка)
M_RIM = pbr("ROOM_pool_rim", "concrete_wall_008", (150, 150, 145), 2.0)
PH = 1.75
for k, (lo, hi) in enumerate([((-PH - 0.42, -PH - 0.30, 0.0), (PH + 0.42, -PH, 0.10)), ((-PH - 0.42, PH, 0.0), (PH + 0.42, PH + 0.30, 0.10)),
                              ((-PH - 0.42, -PH, 0.0), (-PH, PH, 0.10)), ((PH, -PH, 0.0), (PH + 0.42, PH, 0.10))]):
    box(f"PoolLedge_{k}", lo, hi, M_RIM)
# люки гидроакустики (закрыты): деревянный и с синей крышкой — места по скану
box("HatchWood", (-0.82, 1.35, FZ), (-0.335, 1.825, FZ + 0.012), M_HATCH_W)
box("HatchBlue", (1.16, -0.75, FZ), (1.65, -0.29, FZ + 0.008), M_HATCH_B)

# ---------------- мебель, приборы, стенды (размеры и снимки — blender/scan_measure.py, lab_room_items.json)
import json  # noqa: E402

ITEMS = json.load(open(ROOT + "/blender/lab_room_items.json", encoding="utf-8"))
RT = ROOT + "/blender/room_tex"
M_TOP = flat("ROOM_table_top", (212, 148, 58), 0.45)          # жёлтый пластик столешниц (по скану)
M_LEG = flat("ROOM_table_leg", (60, 60, 58), 0.5, 0.8)
M_SEAT = flat("ROOM_chair_seat", (190, 140, 80), 0.5)          # гнутая фанера
M_CASE = flat("ROOM_case_side", (120, 116, 108), 0.6)


def img_mat(name, path, side_col=None):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m["uv_m"] = 1.0
    nt = m.node_tree
    b = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = bpy.data.images.load(path, check_existing=True)
    t.extension = "EXTEND"
    nt.links.new(t.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.55
    return m


def mean_col(path):
    im = bpy.data.images.load(path, check_existing=True)
    import numpy as np
    px = np.empty(im.size[0] * im.size[1] * 4, np.float32)
    im.pixels.foreach_get(px)
    px = px.reshape(-1, 4)[:, :3]
    px = px[px.max(1) > 0.03]
    c = px.mean(0) if len(px) else np.array([0.4, 0.4, 0.4])
    return tuple(int(255 * v ** (1 / 1.0)) for v in c)


def oriented_box(name, o, dv, nv, a0, a1, b0, b1, z0, z1, mats, front=None, top=None):
    """Коробка в осях стола: a вдоль dv, b по nv (в зал), z вверх. mats = [бока, лицо, верх]; UV лица и верха —
    на весь снимок (ось «вправо» снимка = (−n_y, n_x))."""
    dv, nv = Vector((*dv, 0)).normalized(), Vector((*nv, 0)).normalized()
    o = Vector((*o, 0))
    rt = Vector((-nv.y, nv.x, 0))
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    P = lambda a, b, z: o + dv * a + nv * b + Vector((0, 0, z))
    v = [bm.verts.new(P(a, b, z)) for z in (z0, z1) for b in (b0, b1) for a in (a0, a1)]
    faces = [((4, 5, 7, 6), 2), ((0, 2, 3, 1), 0), ((2, 6, 7, 3), 1), ((0, 1, 5, 4), 0), ((0, 4, 6, 2), 0), ((1, 3, 7, 5), 0)]
    fc = P((a0 + a1) / 2, b1, (z0 + z1) / 2)
    tc = P((a0 + a1) / 2, (b0 + b1) / 2, z1)
    w = abs(a1 - a0)
    for idx, mi in faces:
        f = bm.faces.new([v[i] for i in idx])
        f.material_index = mi
        for lp in f.loops:
            c = lp.vert.co
            if mi == 1:
                lp[uvl].uv = ((c - fc).dot(rt) / w + 0.5, (c.z - z0) / (z1 - z0))
            elif mi == 2:
                lp[uvl].uv = ((c - tc).dot(rt) / w + 0.5, (c - tc).dot(-nv) / abs(b1 - b0) + 0.5)
            else:
                lp[uvl].uv = (c.x + c.y, c.z)
    bm.normal_update()
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    for m in mats:
        me.materials.append(m)
    return ob


# столы: столешница 3,5 см + стальные ножки 4 × 4 см по углам и через ≤ 1,4 м (каркас — оценка по снимкам)
for tn, (o, dv, nv, L, D, top) in ITEMS["tables"].items():
    if tn == "N":                                      # северный стол: за уступом стены глубже (до Y 2,95)
        parts = [(0.0, 2.98, D), (2.98, L, D + 0.17)]
    else:
        parts = [(0.0, L, D)]
    for k, (a0, a1, dd) in enumerate(parts):
        oriented_box(f"Table_{tn}{k}", o, dv, nv, a0, a1, 0.0, dd, top - 0.035, top, [M_TOP, M_TOP, M_TOP])
        n_leg = max(2, int(math.ceil((a1 - a0) / 1.4)) + 1)
        for i in range(n_leg):
            a = a0 + 0.04 + (a1 - a0 - 0.08) * i / (n_leg - 1)
            for bb in (0.05, dd - 0.05):
                oriented_box(f"Leg_{tn}{k}_{i}", o, dv, nv, a - 0.02, a + 0.02, bb - 0.02, bb + 0.02, FZ, top - 0.035, [M_LEG] * 3)
        oriented_box(f"Apron_{tn}{k}", o, dv, nv, a0 + 0.02, a1 - 0.02, dd - 0.06, dd - 0.04, top - 0.12, top - 0.035, [M_LEG] * 3)
# приборы — модели (blender/lab_devices.py); места и габариты — по скану (scan_measure.py) и развёрткам стен
sys.path.insert(0, ROOT + "/blender")
import lab_devices  # noqa: E402

DEV_KIND = {"Dev_N0": "amp", "Dev_N1": "osc", "Dev_W4": "gen", "Dev_W6": "rx", "Dev_S8": "case", "Dev_S10": "psu", "Dev_E11": "psu"}
DEV_FIX = {"Dev_N1": dict(b=[0.26, 0.52])}             # осциллограф: на скане разбит на две области по высоте
dev_by = {d["name"]: d for d in ITEMS["devices"]}
for nm, kind in DEV_KIND.items():
    d = dict(dev_by[nm])
    d.update(DEV_FIX.get(nm, {}))
    lab_devices.build(coll, nm, kind, d["o"], d["dv"], d["nv"], d["a"][0], d["a"][1], d["b"][0], d["b"][1], d["z"][0], d["z"][1])
# дополнительные — по развёрткам северной и южной стен (на карте высот слились с соседями)
T = ITEMS["tables"]
for nm, tn, kind, a, b, z in [("Dev_N5", "N", "osc", (2.78, 3.08), (0.25, 0.55), (1.03, 1.47)),
                              ("Dev_S11", "S", "gen", (1.78, 2.23), (0.15, 0.50), (1.04, 1.24)),
                              ("Dev_S12", "S", "gen", (1.80, 2.21), (0.17, 0.48), (1.24, 1.45))]:
    o, dv_, nv_ = T[tn][0], T[tn][1], T[tn][2]
    lab_devices.build(coll, nm, kind, o, dv_, nv_, a[0], a[1], b[0], b[1], z[0], z[1])
# шкафы — модели (blender/lab_devices.py), стенды и плакаты — свои текстуры (blender/make_room_textures.py)
CAB_KIND = {"Cab_SE_wardrobe": "wardrobe", "Cab_S_glass": "glass_cabinet", "Cab_SW_grey": "metal_cabinet", "Cab_WZ_books": "bookcase"}
for it in ITEMS["items"]:
    n = Vector((*it["n"], 0)).normalized()
    rt = Vector((-n.y, n.x, 0))
    c = Vector(it["c"])
    if it["kind"] == "cabinet":
        lab_devices.build_at(coll, it["name"], CAB_KIND[it["name"]], c - rt * (it["w"] / 2), rt, -n, c.z, it["w"], it["d"], it["h"])
        continue
    o = c - rt * (it["w"] / 2)
    oriented_box(it["name"], (o.x, o.y), (rt.x, rt.y), (n.x, n.y), 0.0, it["w"], -it["d"], 0.0, c.z, c.z + it["h"],
                 [M_FRAME, img_mat(f"ROOM_{it['name']}", f"{RT}/own_{it['name']}.png"), M_FRAME])
# знак «Курить запрещено» на сером шкафу (место — по снимку скана)
sg = bpy.data.objects["Cab_SW_grey"]
oriented_box("Sign_nosmoke", (-3.85, -2.765), (1, 0), (0, 1), 0.0, 0.15, -0.002, 0.0, 1.72, 1.87,
             [M_FRAME, img_mat("ROOM_sign", f"{RT}/own_sign_nosmoke.png"), M_FRAME])
# центральный стол у открытого люка (по скану: столешница Z 1,02, X −1,05…0,55, Y −0,85…−0,17), прибор на нём,
# картонные коробки под ним
ITEMS["tables"]["C"] = ((-1.05, -0.17), (1.0, 0.0), (0.0, -1.0), 1.60, 0.68, 1.02)
o, dv_, nv_, L, D, top = ITEMS["tables"]["C"]
oriented_box("Table_C0", o, dv_, nv_, 0.0, L, 0.0, D, top - 0.035, top, [M_TOP, M_TOP, M_TOP])
for i, a in enumerate((0.04, L / 2, L - 0.04)):
    for bb in (0.05, D - 0.05):
        oriented_box(f"Leg_C_{i}{bb:.2f}", o, dv_, nv_, a - 0.02, a + 0.02, bb - 0.02, bb + 0.02, FZ, top - 0.035, [M_LEG] * 3)
lab_devices.build(coll, "Dev_C1", "psu", (-1.05, -0.85), (1.0, 0.0), (0.0, 1.0), 0.95, 1.55, 0.27, 0.57, top, top + 0.40)
M_CARD = img_mat("ROOM_cardboard", f"{RT}/own_cardboard.png")
for k, (xa, xb, ya, yb, zt) in enumerate([(-0.25, 0.25, -0.75, -0.30, 0.60), (0.27, 0.65, -0.74, -0.34, 0.58), (0.30, 0.80, -1.20, -0.80, 0.83)]):
    oriented_box(f"Carton_{k}", (xa, ya), (1, 0), (0, 1), 0.0, xb - xa, 0.0, yb - ya, FZ, zt, [M_CARD, M_CARD, M_CARD])
# стулья у столов (места сидений по скану: Z сиденья 0,75; фанера и стальные ножки — оценка по снимкам)
CHAIRS = [(-1.82, 1.93, 90), (-1.45, 1.93, 90), (0.87, 1.62, 70), (-1.95, -1.08, 0), (-1.95, -1.62, 0),
          (-4.72, -1.52, 180), (-3.38, -2.02, 200), (1.42, -2.12, -90)]
for k, (x, y, a) in enumerate(CHAIRS):
    parts = [box(f"Chair_{k}_seat", (-0.21, -0.21, 0.72), (0.21, 0.21, 0.75), M_SEAT),
             box(f"Chair_{k}_back", (-0.21, 0.19, 0.95), (0.21, 0.215, 1.22), M_SEAT)]
    for i, (lx, ly) in enumerate([(-0.18, -0.18), (0.18, -0.18), (-0.18, 0.18), (0.18, 0.18)]):
        parts.append(box(f"Chair_{k}_leg{i}", (lx - 0.012, ly - 0.012, FZ), (lx + 0.012, ly + 0.012, 0.72), M_LEG))
    for px_ in (-0.14, 0.14):                          # спинка на двух стальных трубках
        parts.append(box(f"Chair_{k}_post{px_:+.2f}", (px_ - 0.009, 0.192, 0.74), (px_ + 0.009, 0.21, 1.0), M_LEG))
    for o_ in parts:
        o_.rotation_euler = (0, 0, math.radians(a + 90))
        o_.location = (x, y, 0)

bpy.ops.wm.save_as_mainfile(filepath=ROOT + "/blender/lab_room.blend")
tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in coll.objects if o.type == "MESH")
print("ROOM треугольников", tris, "объектов", len(coll.objects), flush=True)
