"""Место крушения для сцены «корабль» (этап 4, доработка): дно, судно-скан, ил, якорь, обломки.

Запуск без окна (после build_wreck_scan.py, который пишет blender/wreck_scan.blend):
    blender -b --factory-startup --python blender/build_wreck_site.py -- [--render <папка>]
Пишет godot/assets/wreck/wreck_site.glb и blender/wreck_site_report.json.

Как устроено место (по наблюдениям за затонувшими судами на мягком грунте, оценка):
 - дно 40 × 40 м на 8 м, мягкие волны рельефа ±0,3 м, дальше 14 м холмы; пятна песка с рябью на иле
   (маска в цвете вершин: R = доля песка);
 - судно (скан Malpas, CC BY 4.0) стоит курсом 30°, крен 8° на правый борт, нос чуть ниже (1°),
   срез скана по линии ила утоплен на 0,15 м;
 - вокруг корпуса: размыв (ямы до 0,35 м) у носа и кормы, где течение огибает корпус, и нанос ила
   до 0,7 м у левого борта (подветренная сторона): так корпус «затянут илом» и срез скана скрыт;
 - якорь Холла на дне перед носом, цепь от клюза частично в иле; 2 бочки, ящик, покрышка, камни;
 - жизнь и мелочь (оценка по видам Балтики и Белого моря на 5-10 м): ламинария и пучки водорослей на
   верхних гранях корпуса и камнях, актинии Metridium гроздьями на бортах, морские звёзды, луга зостеры
   на песке, створки, следы роющих животных (холмики и воронки), галька, листы обшивки, труба, трос,
   бутылки; пустые объекты Home_* — места рыб, камбалы и крабов (их двигает Godot, game/fauna.gd).
Материалы называются как наборы текстур Poly Haven (MAT_<набор>), Godot подставляет текстуры по имени.
Точки осмотра: пустые объекты IP_1..IP_6 (имена ниже).
"""
import json
import math
import os
import random
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Euler, Matrix, Vector, kdtree

ROOT = "D:/Документы/ROV-Sim"
SCAN = ROOT + "/blender/wreck_scan.blend"
GLB = ROOT + "/godot/assets/wreck/wreck_site.glb"
REPORT = ROOT + "/blender/wreck_site_report.json"
TEX = ROOT + "/godot/assets/textures"

RES = 0.25                    # шаг сетки дна у судна, м
HEADING = 30.0                # курс судна, ° по часовой сверху
HEEL = 8.0                    # крен на правый борт, °
TRIM = -1.0                   # дифферент (нос вниз), °
SINK = 0.15                   # насколько срез скана ниже среднего дна, м
HALF_L, HALF_B = 5.1, 2.5     # полудлина и полуширина корпуса в плане (из отчёта скана)

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
render_dir = argv[argv.index("--render") + 1] if "--render" in argv else None


def log(*a):
    print("SITE", *a, flush=True)


bpy.ops.wm.open_mainfile(filepath=SCAN)
hull = bpy.data.objects["WreckHull"]
coll = bpy.context.scene.collection

# ---------------- материалы (превью Blender; в Godot подменяются по имени) ----------------
def tex_mat(name, set_name, scale=1.0, color_mix=None):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapn = nt.nodes.new("ShaderNodeMapping")
    mapn.inputs["Scale"].default_value = (scale, scale, scale)
    nt.links.new(coord.outputs["UV"], mapn.inputs["Vector"])
    d = f"{TEX}/{set_name}/{set_name}"
    img = nt.nodes.new("ShaderNodeTexImage")
    img.image = bpy.data.images.load(f"{d}_diff_1k.jpg", check_existing=True)
    nt.links.new(mapn.outputs["Vector"], img.inputs["Vector"])
    nimg = nt.nodes.new("ShaderNodeTexImage")
    nimg.image = bpy.data.images.load(f"{d}_nor_gl_1k.jpg", check_existing=True)
    nimg.image.colorspace_settings.name = "Non-Color"
    nt.links.new(mapn.outputs["Vector"], nimg.inputs["Vector"])
    nmap = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(nimg.outputs["Color"], nmap.inputs["Color"])
    nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    bsdf.inputs["Roughness"].default_value = 0.95
    if color_mix:      # смесь с вторым набором по цвету вершин (R)
        img2 = nt.nodes.new("ShaderNodeTexImage")
        img2.image = bpy.data.images.load(f"{TEX}/{color_mix}/{color_mix}_diff_1k.jpg", check_existing=True)
        nt.links.new(mapn.outputs["Vector"], img2.inputs["Vector"])
        tattr = nt.nodes.new("ShaderNodeVertexColor")      # крупные пятна тона (против повторения)
        tattr.layer_name = "Col"
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        nt.links.new(tattr.outputs["Alpha"], mix.inputs["Factor"])   # альфа = доля песка
        nt.links.new(img.outputs["Color"], mix.inputs[6])
        nt.links.new(img2.outputs["Color"], mix.inputs[7])
        mul = nt.nodes.new("ShaderNodeMix")
        mul.data_type = "RGBA"
        mul.blend_type = "MULTIPLY"
        mul.inputs[0].default_value = 1.0
        nt.links.new(mix.outputs[2], mul.inputs[6])
        nt.links.new(tattr.outputs["Color"], mul.inputs[7])
        nt.links.new(mul.outputs[2], bsdf.inputs["Base Color"])
    else:
        nt.links.new(img.outputs["Color"], bsdf.inputs["Base Color"])
    return m


def plain_mat(name, col, rough=0.8, metal=0.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*col, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    return m


M_SEABED = tex_mat("MAT_brown_mud_02__brown_mud_rocks_01", "brown_mud_02", 1.0, "brown_mud_rocks_01")
M_RUST = tex_mat("MAT_rust_coarse_01", "rust_coarse_01", 1.0)
M_RUST2 = tex_mat("MAT_green_metal_rust__rust_coarse_01", "green_metal_rust", 1.5, "rust_coarse_01")   # краска + ржавчина по маске, UV бочки в метрах
M_ROCK = tex_mat("MAT_rock_boulder_dry", "rock_boulder_dry", 1.0)
M_WOOD = plain_mat("MAT_rotten_wood", (0.10, 0.075, 0.05), 0.9)
M_RUBBER = plain_mat("MAT_old_rubber", (0.03, 0.03, 0.03), 0.9)


# ---------------- судно: поза ----------------
ship_rot = Euler((math.radians(TRIM), math.radians(HEEL), math.radians(-HEADING)), "XYZ").to_matrix().to_4x4()
ship_m = Matrix.Translation((0, 0, -SINK)) @ ship_rot
hull.matrix_world = ship_m
inv = ship_m.inverted()


def to_ship(x, y, z=0.0):
    p = inv @ Vector((x, y, z))
    return p.x, p.y


# ---------------- дно ----------------
# Две сетки, сшитые без щелей: мелкая 0,25 м в квадрате ±FINE у судна (там вся жизнь) и крупная COARSE м
# до ±FAR м, чтобы край сцены не был виден (у края вода к тому же мутнеет, game/tether.gd). На стыке
# крупные клетки, соседние с мелкой сеткой, — веера треугольников к её узлам (длинных тонких треугольников
# нет: видеокарта считает свет на каждый, тонкие обходятся очень дорого).
FINE = 12.0
COARSE = 2.0
FAR = 60.0
c, s = math.cos(math.radians(HEADING)), math.sin(math.radians(HEADING))


def value_noise(X, Y, scale, seed):
    """Гладкий шум: сумма синусоид со случайными направлениями (детерминированно)."""
    r = np.random.default_rng(seed)
    h = np.zeros_like(X)
    for _ in range(6):
        a = r.uniform(0, 2 * np.pi)
        k = 2 * np.pi / (scale * r.uniform(0.7, 1.4))
        h += np.sin(k * (X * np.cos(a) + Y * np.sin(a)) + r.uniform(0, 2 * np.pi))
    return h / 6


def field(X, Y):
    """Высота H, доля гравия, тон и расстояние до борта D в точках X, Y (массивы)."""
    Rr = np.hypot(X, Y)
    near = np.clip((24.0 - Rr) / 8.0, 0, 1)                     # мелкие детали гаснут к краю
    H = 0.30 * value_noise(X, Y, 9.0, 1) + 0.08 * value_noise(X, Y, 3.0, 2) * near
    # координаты в осях судна (без учёта крена: только курс)
    U = X * s + Y * c              # вдоль судна (к носу), курс 30° по часовой: нос = (sin, cos)
    V = X * c - Y * s              # поперёк (к правому борту)
    # расстояние до контура корпуса в плане (эллипс со сплющенными концами)
    E = np.sqrt((U / HALF_L) ** 2 + (V / HALF_B) ** 2)
    D = np.maximum(E - 1.0, 0.0) * HALF_B                       # примерно метры от борта
    port = V < 0
    # нанос ила у левого борта (подветренная сторона) и общий «вал» у корпуса
    H += np.where(port, 0.70, 0.30) * np.exp(-D / np.where(port, 1.6, 0.8)) * (1 - 0.3 * np.abs(U) / HALF_L)
    # ямы размыва у носа и кормы: подковообразный и кормовой вихри вымывают ил (Quinn 2006), до 0,6 м;
    # мелкий ил уносится взвесью, на дне остаётся грубый осадок — гравий и битая ракушка
    ends = np.clip((np.abs(U) - HALF_L * 0.55) / (HALF_L * 0.5), 0, 1)
    pit = ends * np.exp(-((D - 1.0) / 0.9) ** 2)
    H -= 0.6 * pit
    # «след» размыва за кормой по течению (пологая ложбина до 6 м)
    H -= 0.15 * np.exp(-(V / 1.6) ** 2) * np.clip((-U - HALF_L) / 1.0, 0, 1) * np.exp(-np.clip(-U - HALF_L, 0, None) / 4.0)
    # под корпусом дно поднято до линии ила (скрыть срез скана)
    H = np.where(E < 1.0, np.maximum(H, 0.25), H)
    # маска гравия (альфа цвета вершин): ямы размыва, полоса у правого борта (промыто), пятна около судна
    sand = np.clip(1.6 * pit + 0.7 * np.exp(-D / 0.7) * np.where(port, 0.2, 1.0)
                   + np.clip(1.4 * value_noise(X, Y, 4.0, 4) - 0.5, 0, 1) * np.clip((9.0 - D) / 4.0, 0, 1), 0, 1)
    # крупные пятна тона: органический ил темнее (0,7), промытые участки светлее (1,1); у корпуса темнее
    TONE = np.clip(0.9 + 0.22 * value_noise(X, Y, 5.0, 6) + 0.08 * value_noise(X, Y, 1.7, 7), 0.65, 1.15)
    TONE = np.where(D < 1.5, TONE * 0.85, TONE)
    # мелкие бугры и ямки ила (следы роющих животных, комья): ±3 см на 1-2 м
    H += 0.03 * value_noise(X, Y, 1.3, 8) * (1 - sand) * near
    return H, sand, TONE, D


xs = np.arange(-FINE, FINE + 1e-6, RES)            # мелкая сетка
n = len(xs)
X, Y = np.meshgrid(xs, xs, indexing="xy")
H, sand, TONE, D = field(X, Y)
xc = np.arange(-FAR, FAR + 1e-6, COARSE)           # крупная сетка (её узлы на ±FINE совпадают с мелкими)
nc = len(xc)
Xc, Yc = np.meshgrid(xc, xc, indexing="xy")
Hc, sand_c, TONE_c, D_c = field(Xc, Yc)

bm = bmesh.new()
uv_l = bm.loops.layers.uv.new("UVMap")
col_l = bm.loops.layers.color.new("Col")       # RGB: тон крупных пятен, A: доля гравия (один слой для glTF)


def face(pts, cols):
    """Грань по точкам (x, y, z) с цветом (тон, гравий) у каждой; UV — текстура 3 × 3 м."""
    f = bm.faces.new([bm.verts.new(p_) for p_ in pts])
    for lp, (tb, sv) in zip(f.loops, cols):
        co = lp.vert.co
        lp[uv_l].uv = (co.x / 3.0, co.y / 3.0)
        lp[col_l] = (tb / 1.15, tb * 0.98 / 1.15, tb * 0.95 / 1.15, sv)    # тон /1,15: цвет в [0, 1]


def fpt(i, j):
    return (xs[i], xs[j], H[j, i]), (TONE[j, i], sand[j, i])


def cpt(i, j):
    return (xc[i], xc[j], Hc[j, i]), (TONE_c[j, i], sand_c[j, i])


for j in range(n - 1):
    for i in range(n - 1):
        q = [fpt(i, j), fpt(i + 1, j), fpt(i + 1, j + 1), fpt(i, j + 1)]
        face([a[0] for a in q], [a[1] for a in q])
k = int(round(COARSE / RES))                     # мелких шагов в крупном
for j in range(nc - 1):
    for i in range(nc - 1):
        x0, x1, y0, y1 = xc[i], xc[i + 1], xc[j], xc[j + 1]
        if x0 >= -FINE - 1e-6 and x1 <= FINE + 1e-6 and y0 >= -FINE - 1e-6 and y1 <= FINE + 1e-6:
            continue                              # внутри мелкой сетки
        q = [cpt(i, j), cpt(i + 1, j), cpt(i + 1, j + 1), cpt(i, j + 1)]
        # сторона клетки на границе мелкой сетки: веер к её узлам
        edge = None
        in_x = x0 >= -FINE - 1e-6 and x1 <= FINE + 1e-6
        in_y = y0 >= -FINE - 1e-6 and y1 <= FINE + 1e-6
        fi = lambda x: int(round((x + FINE) / RES))
        if in_x and abs(y1 + FINE) < 1e-6:        # клетка под мелкой сеткой: верхняя сторона
            edge = [fpt(ii, 0) for ii in range(fi(x1), fi(x0) - 1, -1)]
            far_ = [q[0], q[1]]
        elif in_x and abs(y0 - FINE) < 1e-6:      # над: нижняя сторона
            edge = [fpt(ii, n - 1) for ii in range(fi(x0), fi(x1) + 1)]
            far_ = [q[2], q[3]]
        elif in_y and abs(x1 + FINE) < 1e-6:      # слева: правая сторона
            edge = [fpt(0, jj) for jj in range(fi(y0), fi(y1) + 1)]
            far_ = [q[3], q[0]]
        elif in_y and abs(x0 - FINE) < 1e-6:      # справа: левая сторона
            edge = [fpt(n - 1, jj) for jj in range(fi(y1), fi(y0) - 1, -1)]
            far_ = [q[1], q[2]]
        if edge is None:
            face([a[0] for a in q], [a[1] for a in q])
            continue
        # веер: дальние углы far_[0], far_[1] и узлы мелкой стороны (порядок — против часовой сверху)
        mid = len(edge) // 2
        for t in range(mid):
            face([far_[1][0], edge[t][0], edge[t + 1][0]], [far_[1][1], edge[t][1], edge[t + 1][1]])
        face([far_[1][0], edge[mid][0], far_[0][0]], [far_[1][1], edge[mid][1], far_[0][1]])
        for t in range(mid, len(edge) - 1):
            face([far_[0][0], edge[t][0], edge[t + 1][0]], [far_[0][1], edge[t][1], edge[t + 1][1]])
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)     # общие вершины: гладкие нормали без швов
me = bpy.data.meshes.new("Seabed")
bm.to_mesh(me)
bm.free()
for p in me.polygons:
    p.use_smooth = True
seabed = bpy.data.objects.new("Seabed", me)
coll.objects.link(seabed)
seabed.data.materials.append(M_SEABED)


def _bilinear(grid, Z, x, y):
    m = len(grid)
    i = min(max(int(np.searchsorted(grid, x)) - 1, 0), m - 2)
    j = min(max(int(np.searchsorted(grid, y)) - 1, 0), m - 2)
    tx = (x - grid[i]) / (grid[i + 1] - grid[i])
    ty = (y - grid[j]) / (grid[j + 1] - grid[j])
    return float(Z[j, i] * (1 - tx) * (1 - ty) + Z[j, i + 1] * tx * (1 - ty)
                 + Z[j + 1, i] * (1 - tx) * ty + Z[j + 1, i + 1] * tx * ty)


def ground(x, y):
    """Высота дна в точке (билинейно по мелкой или крупной сетке — как лежат грани)."""
    if abs(x) <= FINE and abs(y) <= FINE:
        return _bilinear(xs, H, x, y)
    return _bilinear(xc, Hc, x, y)


# ---------------- предметы ----------------
def obj_from_bm(name, bm, mat, loc, rot=(0, 0, 0)):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    coll.objects.link(o)
    o.data.materials.append(mat)
    o.location = loc
    o.rotation_euler = Euler([math.radians(a) for a in rot])
    for p in o.data.polygons:
        p.use_smooth = True
    o.data.uv_layers.new(name="UVMap") if not o.data.uv_layers else None
    return o


def cylinder(name, r, h, mat, loc, rot=(0, 0, 0), seg=12):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r, radius2=r, depth=h, calc_uvs=True)
    return obj_from_bm(name, bm, mat, loc, rot)


def box(name, size, mat, loc, rot=(0, 0, 0)):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, calc_uvs=True)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    return obj_from_bm(name, bm, mat, loc, rot)


def torus(name, R, r, mat, loc, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r, major_segments=24, minor_segments=8,
                                     location=loc, rotation=[math.radians(a) for a in rot])
    o = bpy.context.active_object
    o.name = name
    o.data.materials.append(mat)
    return o


def rock(name, size, loc, seed):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=1.0, calc_uvs=True)
    r = random.Random(seed)
    dirs = [Vector((r.uniform(-1, 1), r.uniform(-1, 1), r.uniform(-1, 1))).normalized() for _ in range(5)]
    for v in bm.verts:
        bump = sum(0.22 * max(v.co.normalized().dot(d), 0) ** 3 for d in dirs)    # грани и сколы
        v.co *= 1.0 + r.uniform(-0.06, 0.06) - bump
        if v.co.z < -0.2:
            v.co.z = -0.2 - (v.co.z + 0.2) * 0.3                                   # плоское основание
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    o = obj_from_bm(name, bm, M_ROCK, loc, (r.uniform(0, 12), r.uniform(0, 12), r.uniform(0, 360)))
    for p in o.data.polygons:
        p.use_smooth = False
    return o


def world_of_ship(p):
    return ship_m @ Vector(p)


# якорь Холла: веретено, лапы, скоба; лежит перед носом на боку
bow_tip = world_of_ship((0, HALF_L - 0.2, 1.0))
fwd = Vector((s, c, 0))
anchor_xy = bow_tip + fwd * 3.2 + Vector((-c, s, 0)) * 1.4
az = ground(anchor_xy.x, anchor_xy.y)
def hall_anchor(name, mat):
    """Якорь Холла ~1,2 м (≈100 кг): веретено сужается к голове, коробка лап, две лапы под 40° с
    приливами на концах. Оси: веретено вдоль +Y (голова), лапы в плоскости XY, отогнуты к −Z."""
    bm = bmesh.new()

    def prism(pts_bottom, h):
        vs = [bm.verts.new(p) for p in pts_bottom] + [bm.verts.new((p[0], p[1], p[2] + h)) for p in pts_bottom]
        n = len(pts_bottom)
        bm.faces.new(vs[:n][::-1])
        bm.faces.new(vs[n:])
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new([vs[i], vs[j], vs[n + j], vs[n + i]])
    # веретено: 8-гранная призма, сужение 0,08 -> 0,05
    seg, L = 8, 1.0
    ring0 = [bm.verts.new((0.04 * math.cos(2 * math.pi * i / seg), 0.0, 0.04 * math.sin(2 * math.pi * i / seg))) for i in range(seg)]
    ring1 = [bm.verts.new((0.026 * math.cos(2 * math.pi * i / seg), L, 0.026 * math.sin(2 * math.pi * i / seg))) for i in range(seg)]
    for i in range(seg):
        j = (i + 1) % seg
        bm.faces.new([ring0[i], ring0[j], ring1[j], ring1[i]])
    bm.faces.new(ring0[::-1])
    bm.faces.new(ring1)
    # коробка лап (крон)
    prism([(-0.22, -0.09, -0.07), (0.22, -0.09, -0.07), (0.22, 0.09, -0.07), (-0.22, 0.09, -0.07)], 0.14)
    # лапы: клинья от крона к голове, приливы (утолщения) на концах
    for sgn in (-1, 1):
        x0 = sgn * 0.17
        prism([(x0 - 0.07, 0.0, -0.03), (x0 + 0.07, 0.0, -0.03), (x0 + sgn * 0.02 + 0.03, 0.46, -0.02),
               (x0 + sgn * 0.02 - 0.03, 0.46, -0.02)], 0.05)
        prism([(x0 + sgn * 0.02 - 0.05, 0.44, -0.035), (x0 + sgn * 0.02 + 0.05, 0.44, -0.035),
               (x0 + sgn * 0.02 + 0.04, 0.52, -0.03), (x0 + sgn * 0.02 - 0.04, 0.52, -0.03)], 0.07)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    coll.objects.link(o)
    o.data.materials.append(mat)
    # развёртка по кубу (для текстуры ржавчины)
    for ob in bpy.context.view_layer.objects:      # только якорь: иначе развёртка ляжет и на корпус
        ob.select_set(False)
    bpy.context.view_layer.objects.active = o
    o.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.cube_project(cube_size=0.5)
    bpy.ops.object.mode_set(mode="OBJECT")
    o.select_set(False)
    bev = o.modifiers.new("Bevel", "BEVEL")          # литьё: скруглённые кромки
    bev.width = 0.012
    bev.segments = 2
    bev.limit_method = "ANGLE"
    o.modifiers.new("WN", "WEIGHTED_NORMAL")
    return o


M_RUST_FINE = tex_mat("MAT_rust_coarse_01__fine", "rust_coarse_01", 3.0)
anc = hall_anchor("Anchor", M_RUST_FINE)
yaw = math.radians(-HEADING + 115)
anc.location = (anchor_xy.x, anchor_xy.y, az + 0.06)                   # лапы и крон чуть в иле
anc.rotation_euler = Euler((math.radians(-4), math.radians(3), yaw))    # лежит плашмя, лапы в грунте
shackle_obj = torus("AnchorShackle", 0.06, 0.016, M_RUST_FINE, (0, 1.05, 0), (0, 90, 0))
shackle_obj.parent = anc
bpy.context.view_layer.update()
shackle = shackle_obj.matrix_world.translation.copy()
# цепь: от клюза по воздуху к дну, затем по дну к якорю, местами в иле
# клюз на левой скуле (якорь лежит слева от носа): точка на поверхности скана (луч снаружи к диаметральной плоскости, оси скана = оси судна)
ok_h, hp_, hn_, _hi = hull.ray_cast(Vector((-2.5, 3.0, 1.5)), Vector((1.0, 0.0, 0.0)))   # форштевень скана — у y ≈ 3,5 м
hawse = (world_of_ship(tuple(hp_ + hn_.normalized() * 0.04)) if ok_h else world_of_ship((0.35, HALF_L - 0.6, 1.7)))
log("клюз", ok_h, tuple(round(v, 2) for v in hawse))
# путь цепи: от клюза провисом к дну у носа, затем по дну с изгибом к скобе якоря
touch = Vector((hawse.x, hawse.y, 0)) + fwd * 0.4 + Vector((-c, s, 0)) * 0.35   # цепь слабая: почти отвесно к дну
path = [hawse]
for k in range(1, 9):
    t = k / 8
    q = hawse.lerp(touch, t)
    q.z = hawse.z * (1 - t) ** 1.7 + ground(q.x, q.y) * (1 - (1 - t) ** 1.7)
    path.append(q)
lat = Vector((-c, s, 0))
for k in range(1, 25):
    t = k / 24
    q = touch.lerp(shackle, t) + lat * 0.6 * math.sin(math.pi * t)
    gq = ground(q.x, q.y)
    q.z = gq + 0.02 if t < 0.95 else gq + (shackle.z - gq) * (t - 0.95) / 0.05
    path.append(q)
links = [path[0]]
for a, b in zip(path[:-1], path[1:]):           # звенья через 7,5 см (звено 9 см)
    m = max(1, int((b - a).length / 0.075))
    for i in range(1, m + 1):
        links.append(a.lerp(b, i / m))
N = len(links)
chain = []
for k in range(N - 1):
    a, b = links[k], links[k + 1]
    d = b - a
    o = torus("ChainLink_%02d" % k, 0.045, 0.012, M_RUST_FINE, (a + b) / 2)
    o.rotation_euler = d.to_track_quat("X", "Z").to_euler()
    o.rotation_euler.rotate_axis("X", math.radians(90 * (k % 2)))
    o.scale = (1.0, 0.62, 1.0)
    chain.append(o)
for ob in bpy.context.view_layer.objects:        # звенья — один объект (один вызов отрисовки вместо ~110)
    ob.select_set(ob in chain)
bpy.context.view_layer.objects.active = chain[0]
bpy.ops.object.join()
chain[0].name = "AnchorChain"
chain = [chain[0]]

def drum(name, mat, loc, rot, seed, crush=0.0, ground_z=0.0):
    """Стальная бочка 200 л (ГОСТ 13950 / тип 55 галлонов): Ø 0,57-0,59 м, высота 0,88 м, завальцованные
    ободки (зиги) по торцам, два ребра качения на ±0,15 м, утопленные днища, две пробки на верхнем днище.
    Профиль вращается (32 сегмента); вмятины — гауссовы вдавливания стенки (crush: доля смятия, лежачие)."""
    P = [(0.0, -0.425), (0.262, -0.425), (0.272, -0.437), (0.284, -0.44), (0.292, -0.43), (0.290, -0.415),
         (0.286, -0.405), (0.286, -0.345), (0.286, -0.285), (0.286, -0.225), (0.286, -0.165), (0.296, -0.150),
         (0.286, -0.135), (0.286, -0.07), (0.286, 0.0), (0.286, 0.07), (0.286, 0.135), (0.296, 0.150),
         (0.286, 0.165), (0.286, 0.225), (0.286, 0.285), (0.286, 0.345), (0.286, 0.405), (0.290, 0.415), (0.292, 0.43), (0.284, 0.44), (0.272, 0.437),
         (0.262, 0.425), (0.0, 0.425)]
    bm = bmesh.new()
    vs = [bm.verts.new((r, 0.0, z)) for r, z in P]
    es = [bm.edges.new((a, b)) for a, b in zip(vs[:-1], vs[1:])]
    bmesh.ops.spin(bm, geom=vs + es, cent=(0, 0, 0), axis=(0, 0, 1), angle=2 * math.pi, steps=40, use_merge=True)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)       # наружу (Godot рисует только лицевые стороны)
    r = random.Random(seed)
    dents = [(r.uniform(0, 2 * math.pi), r.uniform(-0.3, 0.3), r.uniform(0.012, 0.03) + crush * 0.08,
              r.uniform(0.07, 0.14)) for _ in range(r.randint(2, 4))]
    for v in bm.verts:
        rad = math.hypot(v.co.x, v.co.y)
        if rad < 0.2:
            continue
        a = math.atan2(v.co.y, v.co.x)
        push = 0.0
        for a0, z0, depth, w in dents:
            da = (a - a0 + math.pi) % (2 * math.pi) - math.pi
            push += depth * math.exp(-((da * 0.29) ** 2 + (v.co.z - z0) ** 2) / (w * w))
        f = max(rad - push, 0.15) / rad
        v.co.x *= f
        v.co.y *= f
    # цилиндрическая развёртка в метрах: u = угол·R, v = высота (текстура ржавчины без растяжения)
    uvl = bm.loops.layers.uv.new("UVMap")
    for fc in bm.faces:
        angs = [math.atan2(lp.vert.co.y, lp.vert.co.x) for lp in fc.loops]
        if max(angs) - min(angs) > math.pi:              # шов развёртки
            angs = [a + 2 * math.pi if a < 0 else a for a in angs]
        for lp, a in zip(fc.loops, angs):
            rad = math.hypot(lp.vert.co.x, lp.vert.co.y)
            if abs(lp.vert.co.z) >= 0.424 and rad < 0.265:   # днища: плоская проекция
                lp[uvl].uv = (lp.vert.co.x + 0.5, lp.vert.co.y + 0.5)
            else:
                lp[uvl].uv = (a * 0.286, lp.vert.co.z)
    # цвет вершин: A — ржавчина (пятна, сильнее на ободках, рёбрах, вмятинах), RGB — тон (тёмный налёт ила
    # на нижних 0,2 м над грунтом); RGB делится на 1,15 (так тон читает шейдер Godot)
    rotm = Euler([math.radians(x) for x in rot]).to_matrix()
    cl = bm.loops.layers.color.new("Col")
    ph = [r.uniform(0, 6.28) for _ in range(6)]
    for fc in bm.faces:
        for lp in fc.loops:
            co = lp.vert.co
            a = math.atan2(co.y, co.x)
            rad = math.hypot(co.x, co.y)
            n = (math.sin(3 * a + ph[0] + 9 * co.z) + math.sin(5 * a + ph[1] - 13 * co.z)
                 + math.sin(2 * a + ph[2] + 21 * co.z)) / 3
            rim = 1.0 if abs(co.z) > 0.40 or abs(abs(co.z) - 0.15) < 0.02 else 0.0
            dent = 1.0 if rad < 0.278 and abs(co.z) < 0.40 else 0.0
            rust = min(max(0.2 + 0.9 * n + 0.5 * rim + 0.4 * dent + 0.3 * crush, 0.0), 1.0)
            hz = (rotm @ co).z + loc[2] - ground_z                      # высота над грунтом
            tone = 0.55 + 0.45 * min(max(hz / 0.25, 0.0), 1.0)
            lp[cl] = (tone / 1.15, tone * 0.97 / 1.15, tone * 0.92 / 1.15, rust)
    o = obj_from_bm(name, bm, mat, loc, rot)
    for p_ in o.data.polygons:
        p_.use_smooth = True
    es_mod = o.modifiers.new("Edges", "EDGE_SPLIT")     # острые кромки ободков, гладкая стенка
    es_mod.split_angle = math.radians(35)
    for k2, ang in enumerate((0.9, 0.9 + math.pi * 0.62)):   # пробки: Ø 70 и 50 мм на радиусе 0,19 м
        rb = 0.035 if k2 == 0 else 0.025
        plug = cylinder(f"{name}_bung{k2}", rb, 0.02, mat, (0.19 * math.cos(ang), 0.19 * math.sin(ang), 0.43))
        plug.parent = o
    return o


# обломки у правого борта и за кормой
side = Vector((c, -s, 0))
stern = world_of_ship((0, -HALF_L, 1.0))
props = []
for k, (u, v, kind) in enumerate([(-1.5, 3.4, "barrel"), (-2.6, 4.2, "barrel_lying"), (1.2, 3.8, "crate"),
                                  (-6.2, 1.0, "tire"), (-6.8, -1.6, "barrel_lying")]):
    p = Vector((0, 0, 0)) + fwd * u + side * v
    g = ground(p.x, p.y)
    rot_z = random.Random(k).uniform(0, 360)
    if kind == "barrel":
        o = drum("Barrel_%d" % k, M_RUST2, (p.x, p.y, g + 0.30), (8, 4, rot_z), k, 0.0, g)          # на 0,15 м в иле
    elif kind == "barrel_lying":
        o = drum("Barrel_%d" % k, M_RUST2, (p.x, p.y, g + 0.20), (90, 0, rot_z), k, 0.4, g)   # лежит, мята, в иле
    elif kind == "crate":
        o = box("Crate_%d" % k, (0.7, 0.5, 0.45), M_WOOD, (p.x, p.y, g + 0.1), (6, -10, rot_z))
    else:
        o = torus("Tire_%d" % k, 0.32, 0.12, M_RUBBER, (p.x, p.y, g + 0.05), (12, 5, rot_z))
    props.append(o)
# камни: валуны (ледниковые, обычны на дне северных морей) группами в 5,5-12 м от судна, не на судне и якоре
rr = random.Random(7)
rocks = []
g = 0
while g < 7:
    a = rr.uniform(0, 2 * math.pi)
    d = rr.uniform(5.5, 12.0)
    gx, gy = d * math.cos(a), d * math.sin(a)
    if (math.hypot((gx * s + gy * c) / (HALF_L + 2.5), (gx * c - gy * s) / (HALF_B + 2.2)) < 1.0
            or (Vector((gx, gy, 0)) - Vector((anchor_xy.x, anchor_xy.y, 0))).length < 2.5):
        continue
    for k in range(rr.randint(2, 5)):
        x, y = gx + rr.uniform(-1.4, 1.4), gy + rr.uniform(-1.4, 1.4)
        sz = rr.uniform(0.12, 0.6) if k else rr.uniform(0.5, 1.0)
        rocks.append(rock("Rock_%d_%d" % (g, k), (sz, sz * rr.uniform(0.7, 1.2), sz * 0.55),
                          (x, y, ground(x, y) + sz * 0.1), g * 10 + k))
    g += 1

# ---------------- мелочь на дне (оценка, docs/levels.md «Живность у судна») ----------------
# Мелкие предметы одного материала собираются в один объект на ячейку CELL × CELL м: Godot отсекает
# ячейки по дальности (в мутной воде дальше 11 м мелочь не видна). Имена: Bio_* и Fine_* — без
# столкновений в Godot, Debris_* — со столкновениями. Материалы BIO_<вид>: двусторонние, цвет = альбедо ×
# тон RGB цвета вершин; альфа цвета вершин — доля колыхания (амплитуду задаёт Godot, BIO_SWAY).
CELL = 6.0
class Batch:
    def __init__(self, name, mat):
        self.name, self.mat = name, mat
        self.v, self.f, self.col, self.uv = [], [], [], []

    def add(self, verts, faces, cols, uv=None):
        """verts — мировые координаты, cols — (r, g, b, a) каждой вершины, uv(p) — развёртка по точке.
        Без развёртки UV = (альфа, синий), UV2 = (красный, зелёный) цвета: в пачках экземпляров рендер Compatibility
        подменяет цвет вершин данными экземпляра, поэтому BIO_* читают цвет и вес колыхания из UV."""
        base = len(self.v)
        self.v += [tuple(p) for p in verts]
        for fc in faces:
            self.f.append(tuple(base + i for i in fc))
            for i in fc:
                self.col.append(tuple(cols[i]))
                self.uv.append(uv(verts[i]) if uv else (cols[i][3], cols[i][2]))

    def build(self, smooth=True):
        me = bpy.data.meshes.new(self.name)
        me.from_pydata(self.v, [], self.f)
        me.uv_layers.new(name="UVMap").data.foreach_set("uv", [x for t in self.uv for x in t])
        me.uv_layers.new(name="UV2").data.foreach_set("uv", [x for t in self.col for x in t[:2]])
        ca = me.color_attributes.new("Col", "FLOAT_COLOR", "CORNER")
        ca.data.foreach_set("color", [x for t in self.col for x in t])
        me.color_attributes.active_color_name = "Col"
        me.color_attributes.default_color_name = "Col"
        me.polygons.foreach_set("use_smooth", [smooth] * len(me.polygons))
        o = bpy.data.objects.new(self.name, me)
        coll.objects.link(o)
        me.materials.append(self.mat)
        log("пакет", self.name, len(self.f), "граней")
        return o


class CellBatch:
    """Пакеты одного вида по ячейкам: имя <prefix>_<i>_<j>."""
    def __init__(self, prefix, mat):
        self.prefix, self.mat, self.cells = prefix, mat, {}

    def at(self, x, y):
        key = (int(math.floor(x / CELL)), int(math.floor(y / CELL)))
        if key not in self.cells:
            self.cells[key] = Batch("%s_%d_%d" % (self.prefix, key[0] + 20, key[1] + 20), self.mat)
        return self.cells[key]

    def build(self, smooth=True):
        """Начало координат пакета — в центре ячейки (Godot отсекает по дальности от него)."""
        for key, b_ in self.cells.items():
            ctr = Vector(((key[0] + 0.5) * CELL, (key[1] + 0.5) * CELL, 0.0))
            b_.v = [tuple(Vector(v) - ctr) for v in b_.v]
            b_.build(smooth).location = ctr


def frame(n, spin=0.0):
    """Поворот 3×3: локальная z по нормали n, поворот spin вокруг неё."""
    n = Vector(n).normalized()
    t = Vector((1, 0, 0)) if abs(n.x) < 0.9 else Vector((0, 1, 0))
    a = n.cross(t).normalized()
    b = n.cross(a)
    return Matrix((a, b, n)).transposed() @ Matrix.Rotation(spin, 3, "Z")


def frame_dir(ax, along, jitter, rng):
    """Поворот 3×3: локальная z по ax, локальная x как можно ближе к along (течение), ± jitter рад."""
    z = Vector(ax).normalized()
    x = Vector(along) - z * Vector(along).dot(z)
    if x.length < 1e-3:
        x = Vector((1, 0, 0)) - z * z.x
    x = x.normalized()
    m = Matrix((x, z.cross(x), z)).transposed()
    return m @ Matrix.Rotation(rng.uniform(-jitter, jitter), 3, "Z")


def ground_n(x, y):
    e = 0.15
    return Vector((-(ground(x + e, y) - ground(x - e, y)) / (2 * e),
                   -(ground(x, y + e) - ground(x, y - e)) / (2 * e), 1.0)).normalized()


def ground_cell(x, y):
    """Тон, доля гравия и расстояние до борта в точке (ближайший узел мелкой или крупной сетки)."""
    if abs(x) <= FINE and abs(y) <= FINE:
        i, j = int(round((x + FINE) / RES)), int(round((y + FINE) / RES))
        return float(TONE[j, i]), float(sand[j, i]), float(D[j, i])
    i, j = int(round((x + FAR) / COARSE)), int(round((y + FAR) / COARSE))
    return float(TONE_c[j, i]), float(sand_c[j, i]), float(D_c[j, i])


def ribbon(base, up, lean, length, width, segs, side, ruffle=0.0, across=3, profile=None, tone=(1, 1, 1), sway_pow=1.5):
    """Лента (лист ламинарии, травинка): ось c(t) = base + up·L·t + lean·L·t²; ширина width·profile(t);
    side — направление ширины у основания; края волнистые (ruffle, м). Альфа = t^sway_pow."""
    up, lean, side = Vector(up).normalized(), Vector(lean), Vector(side)
    prof = profile or (lambda t: 0.2 + 0.8 * math.sin(math.pi * min(t * 1.15, 1.0)) ** 0.6)
    vs, cs, fs = [], [], []
    for k in range(segs + 1):
        t = k / segs
        c_ = Vector(base) + up * (length * t) + lean * (length * t * t)
        tang = (up + lean * (2 * t)).normalized()
        sd = (side - tang * side.dot(tang)).normalized()
        nrm = tang.cross(sd)
        w = width * prof(t) * 0.5
        rf = ruffle * min(t * 3, 1.0) * math.sin(k * 1.5)
        a = t ** sway_pow
        if across == 3:
            vs += [c_ - sd * w + nrm * rf, c_, c_ + sd * w - nrm * rf]
        else:
            vs += [c_ - sd * w, c_ + sd * w]
        cs += [(*tone, a)] * across
        if k:
            o0, o1 = (k - 1) * across, k * across
            for i in range(across - 1):
                fs.append((o0 + i, o0 + i + 1, o1 + i + 1, o1 + i))
    return vs, fs, cs


def tone_of(rgb):
    """Тон цвета вершин для BIO_*: множитель альбедо, в цвете хранится /1,15 (как у дна)."""
    return tuple(min(x / 1.15, 1.0) for x in rgb)


M_SHELL = plain_mat("BIO_shell", (0.36, 0.34, 0.30), 0.8)           # створки двустворчатых
M_ROPE = plain_mat("MAT_old_rope", (0.07, 0.06, 0.04), 0.9)
M_GLASS = plain_mat("MAT_bottle_glass", (0.02, 0.05, 0.025), 0.2)
life = random.Random(2026)


def shell(b, base, nrm, rng):
    """Створка: низкий купол 1,5-4,5 см (6 + 6 + 1 вершин; нижней грани нет — материал двусторонний), наполовину в иле."""
    r = rng.uniform(0.015, 0.045)
    h = r * rng.uniform(0.3, 0.5)
    M = frame((Vector(nrm) + Vector((rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), 0))).normalized(), rng.uniform(0, 6.28))
    tone = tone_of((rng.uniform(0.7, 1.25),) * 3)
    sink = -h * rng.uniform(0.1, 0.5)
    vs = []
    for rr, z in ((r, 0.0), (r * 0.65, h * 0.75)):
        for i in range(6):
            q = 2 * math.pi * i / 6
            vs.append(Vector(base) + M @ Vector((rr * math.cos(q), 0.8 * rr * math.sin(q), z + sink)))
    vs.append(Vector(base) + M @ Vector((-0.2 * r, 0, h + sink)))       # макушка смещена к замку
    fs = [(i, (i + 1) % 6, 6 + (i + 1) % 6, 6 + i) for i in range(6)] + [(12, 6 + i, 6 + (i + 1) % 6) for i in range(6)]
    b.add(vs, fs, [(*tone, 0.0)] * len(vs))


def burrow(b, x, y, rng, big=False):
    """Следы роющих животных на иле: холмик-выброс (пескожил) или вал вокруг норы (у раков-кротов крупнее),
    в центре тёмная воронка. Материал дна, тон и песок — как у дна в этой точке."""
    tb, sv, _ = ground_cell(x, y)
    g = ground(x, y)
    if big:
        rings = ((0.16, 0.0, 1.0), (0.1, 0.04, 0.95), (0.045, 0.03, 0.75), (0.02, 0.0, 0.55))
    elif rng.random() < 0.55:      # холмик-выброс: витой конус
        rings = ((0.05, 0.0, 1.0), (0.032, 0.018, 1.05), (0.014, 0.03, 1.1))
    else:                          # воронка: валик и яма
        rings = ((0.06, 0.0, 1.0), (0.035, 0.012, 0.9), (0.015, -0.02, 0.45))
    vs, cs = [], []
    for rr, z, k in rings:
        for i in range(8):
            q = 2 * math.pi * i / 8 + rr * 30
            px, py = x + rr * math.cos(q) * rng.uniform(0.85, 1.15), y + rr * math.sin(q) * rng.uniform(0.85, 1.15)
            vs.append(Vector((px, py, ground(px, py) + z + (0.006 if z == 0 else 0))))   # край чуть выше дна (без мерцания)
            t = tb * k
            cs.append((t / 1.15, t * 0.98 / 1.15, t * 0.95 / 1.15, sv))
    vs.append(Vector((x, y, g + rings[-1][1] - 0.005)))
    cs.append(cs[-1])
    nr = len(rings)
    fs = [(r_ * 8 + i, r_ * 8 + (i + 1) % 8, r_ * 8 + 8 + (i + 1) % 8, r_ * 8 + 8 + i) for r_ in range(nr - 1) for i in range(8)]
    fs += [(nr * 8, (nr - 1) * 8 + i, (nr - 1) * 8 + (i + 1) % 8) for i in range(8)]
    b.add(vs, fs, cs, uv=lambda p: (p.x / 3.0, p.y / 3.0))


def pebble(b, base, size, rng):
    bm_ = bmesh.new()
    bmesh.ops.create_icosphere(bm_, subdivisions=1, radius=1.0)
    for v in bm_.verts:
        v.co *= rng.uniform(0.8, 1.15)
        v.co.z *= 0.55
    M = Matrix.Rotation(rng.uniform(0, 6.28), 3, "Z") @ Matrix.Diagonal((size, size * rng.uniform(0.6, 1.0), size))
    vs = [Vector(base) + M @ v.co for v in bm_.verts]
    fs = [tuple(v.index for v in f.verts) for f in bm_.faces]
    bm_.free()
    b.add(vs, fs, [(1, 1, 1, 1)] * len(vs), uv=lambda p: (p.x / 0.6 + p.z, p.y / 0.6))


# створки: россыпью и ракушечником в ложбинах; гуще у судна (там же гравий размыва), не под корпусом
B_SHELL = CellBatch("Fine_shells", M_SHELL)
for _ in range(14):
    cx, cy = life.uniform(-11, 11), life.uniform(-11, 11)
    if ground_cell(cx, cy)[2] < 0.6:
        continue
    for _ in range(life.randint(50, 110)):
        x, y = cx + life.gauss(0, 0.5), cy + life.gauss(0, 0.35)
        shell(B_SHELL.at(x, y), (x, y, ground(x, y)), ground_n(x, y), life)
n_sh = 0
while n_sh < 700:
    x, y = life.uniform(-14, 14), life.uniform(-14, 14)
    tb, sv, dd = ground_cell(x, y)
    if dd > 0.2 and life.random() < 0.2 + 0.8 * sv + 0.5 * math.exp(-dd / 2.0):
        shell(B_SHELL.at(x, y), (x, y, ground(x, y)), ground_n(x, y), life)
        n_sh += 1
# следы роющих животных на иле (в гравии размыва их нет)
B_BUR = CellBatch("Fine_burrows", M_SEABED)
n_b = 0
while n_b < 420:
    x, y = life.uniform(-14, 14), life.uniform(-14, 14)
    tb, sv, dd = ground_cell(x, y)
    if dd > 0.8 and sv < 0.3:
        burrow(B_BUR.at(x, y), x, y, life, big=(n_b % 10 == 0))
        n_b += 1
# галька и булыжники: у валунов и в ямах размыва
B_PEB = CellBatch("Fine_pebbles", M_ROCK)
for o in rocks:
    for _ in range(life.randint(8, 20)):
        x, y = o.location.x + life.gauss(0, 1.0), o.location.y + life.gauss(0, 1.0)
        pebble(B_PEB.at(x, y), (x, y, ground(x, y) + 0.005), life.uniform(0.02, 0.1), life)
n_p = 0
while n_p < 260:
    x, y = life.uniform(-12, 12), life.uniform(-12, 12)
    tb, sv, dd = ground_cell(x, y)
    if dd > 0.2 and life.random() < sv:
        pebble(B_PEB.at(x, y), (x, y, ground(x, y)), life.uniform(0.015, 0.07), life)
        n_p += 1
for cb in (B_SHELL, B_BUR):
    cb.build()
B_PEB.build(smooth=False)

# обломки судна у корпуса: листы обшивки, труба, бухта троса, бутылки (листы и труба со столкновениями)
for k, (u, v) in enumerate(((-3.8, -3.6), (1.0, -4.4), (4.4, 3.2), (-7.4, 0.6))):
    p = fwd * u + side * v
    bm_ = bmesh.new()
    bmesh.ops.create_grid(bm_, x_segments=6, y_segments=4, size=0.5)
    lx, ly = life.uniform(0.6, 1.2), life.uniform(0.4, 0.8)
    for vv in bm_.verts:
        vv.co.x *= lx
        vv.co.y *= ly
        vv.co.z = 0.06 * math.sin(vv.co.x * 4 + k) * vv.co.x + 0.04 * vv.co.y ** 2 * 4      # погнут
    uvl = bm_.loops.layers.uv.new("UVMap")
    for f in bm_.faces:
        for lp in f.loops:
            lp[uvl].uv = (lp.vert.co.x, lp.vert.co.y)
    nrm_g = ground_n(p.x, p.y)                 # лежит по склону, край в иле
    o = obj_from_bm("Debris_plate_%d" % k, bm_, M_RUST, (p.x, p.y, ground(p.x, p.y) - 0.01), (0, 0, 0))
    o.rotation_euler = (frame(nrm_g, life.uniform(0, 6.28)) @ Matrix.Rotation(math.radians(life.uniform(-4, 4)), 3, "X")).to_euler()
    sol = o.modifiers.new("Solid", "SOLIDIFY")
    sol.thickness = 0.012
pipe_p = fwd * -0.5 + side * -4.6
cylinder("Debris_pipe", 0.06, 1.6, M_RUST, (pipe_p.x, pipe_p.y, ground(pipe_p.x, pipe_p.y) + 0.03), (90, 0, -HEADING + 70), seg=10)
coil_p = fwd * -5.4 + side * -2.9
for k, sc_ in enumerate((1.0, 0.8, 0.62)):    # бухта троса: три витка, верхние меньше и смещены
    torus("Fine_rope_%d" % k, 0.22 * sc_, 0.025, M_ROPE,
          (coil_p.x + 0.03 * k, coil_p.y, ground(coil_p.x, coil_p.y) + 0.02 + 0.035 * k))
for k, (u, v) in enumerate(((2.8, 3.2), (-4.2, -4.0))):
    p = fwd * u + side * v
    prof = [(0.0, 0.0), (0.035, 0.0), (0.037, 0.02), (0.037, 0.19), (0.03, 0.22), (0.013, 0.25), (0.013, 0.3), (0.0, 0.3)]
    bm_ = bmesh.new()
    vs_ = [bm_.verts.new((r_, 0, z_)) for r_, z_ in prof]
    es_ = [bm_.edges.new((a_, b2)) for a_, b2 in zip(vs_[:-1], vs_[1:])]
    bmesh.ops.spin(bm_, geom=vs_ + es_, cent=(0, 0, 0), axis=(0, 0, 1), angle=2 * math.pi, steps=10, use_merge=True)
    bmesh.ops.remove_doubles(bm_, verts=bm_.verts, dist=1e-5)
    bmesh.ops.recalc_face_normals(bm_, faces=bm_.faces)
    obj_from_bm("Fine_bottle_%d" % k, bm_, M_GLASS, (p.x, p.y, ground(p.x, p.y) + 0.03), (90, life.uniform(-10, 10), life.uniform(0, 360)))

# ---------------- обрастание судна и живность на дне: образцы + экземпляры ----------------
# Затонувшее судно на мягком грунте — искусственный риф: твёрдый корпус обрастает за годы, на северных
# мелководьях больше всего книдарий (Zintzen и др. 2008: у берега преобладает актиния Metridium senile,
# дальше — гидроид Tubularia indivisa), кроме них мягкий коралл Alcyonium digitatum, губки, мидии, морские
# ежи и звёзды, на верхних гранях — ламинария и красные водоросли; на иле у корпуса — офиуры. Виды и
# плотности — оценка. Каждый вид — один образец сетки Proto_<вид> (лежит под дном, в Godot скрыт) и список
# экземпляров (положение, поворот с масштабом, тон) в godot/assets/wreck/wreck_life.json; Godot рисует
# их пачками (MultiMesh) по ячейкам CELL м с отсечением по дальности (game/wreck_life.gd).
CURRENT = Vector((1.0, 0.25, 0.0)).normalized()     # течение у дна (листья ламинарии ложатся по нему), оценка
PROTO_Z = -30.0
PROTOS = {}
INST = {}


def col(sh, a=0.0, rgb=(1.0, 1.0, 1.0)):
    """Цвет вершины образца: оттенок rgb × яркость sh (хранится /1,15), альфа — доля колыхания."""
    return tuple(min(x * sh / 1.15, 1.0) for x in rgb) + (a,)


def make_proto(sp, mat, geo, lod=None):
    """Образец вида и (lod) упрощённый образец Proto_<вид>_lod для дальних ячеек."""
    if lod is not None:
        make_proto(sp + "_lod", mat, lod)
    vs, fs, cs = geo
    b_ = Batch("Proto_" + sp, mat)
    b_.add([Vector(v) for v in vs], fs, cs)
    o = b_.build()
    o.location = (len(PROTOS) * 0.5, 0.0, PROTO_Z)
    PROTOS[sp] = o
    return o


def ring_faces(o0, o1, seg, closed=True):
    return [(o0 + i, o0 + (i + 1) % seg, o1 + (i + 1) % seg, o1 + i) for i in range(seg if closed else seg - 1)]


def g_metridium(lo=False):
    """Metridium senile: столбик r 3 см, h 12 см, воротничок; венец — пышный лопастной диск ∅ ≈ 14 см
    (5 лопастей с мелкой бахромой). Основа в 0, ось +z."""
    vs, cs, fs = [], [], []
    seg = 4 if lo else 6
    for r, z, sh, a in ((0.030, 0.0, 0.55, 0.0), (0.025, 0.08, 0.8, 0.25), (0.033, 0.122, 0.9, 0.5)):
        for i in range(seg):
            q = 2 * math.pi * i / seg
            vs.append((r * math.cos(q), r * math.sin(q), z))
            cs.append(col(sh, a))
    for k in range(2):
        fs += ring_faces(k * seg, (k + 1) * seg, seg)
    n0 = len(vs)
    vs.append((0.0, 0.0, 0.118))
    cs.append(col(0.55, 0.5))
    m = 10 if lo else 20
    for rr, zz, sh in (((0.07, 0.145, 1.0),) if lo else ((0.045, 0.135, 0.95), (0.072, 0.15, 1.05))):
        for i in range(m):
            q = 2 * math.pi * i / m
            lob = 1 + 0.28 * math.sin(5 * q) + 0.08 * math.sin(10 * q + 0.5)
            vs.append((rr * lob * math.cos(q), rr * lob * math.sin(q), zz + 0.02 * math.sin(5 * q + 1.0) + 0.006 * math.sin(13 * q)))
            cs.append(col(sh, 1.0))
    fs += [(n0, n0 + 1 + i, n0 + 1 + (i + 1) % m) for i in range(m)]
    if not lo:
        fs += ring_faces(n0 + 1, n0 + 1 + m, m)
    return vs, fs, cs


def g_hydroid(rng, lo=False):
    """Tubularia indivisa: куст из 7 стеблей 5-12 см с розовыми головками (два венчика щупалец)."""
    vs, cs, fs = [], [], []
    for _ in range(3 if lo else 7):
        bx, by = rng.uniform(-0.02, 0.02), rng.uniform(-0.02, 0.02)
        h = rng.uniform(0.05, 0.12)
        tip = Vector((bx + rng.uniform(-0.03, 0.03), by + rng.uniform(-0.03, 0.03), h))
        v_, f_, c_ = ribbon((bx, by, 0), tip - Vector((bx, by, 0)), (0, 0, 0), (tip - Vector((bx, by, 0))).length, 0.003, 1,
                            Vector((1, 0, 0)), across=2, tone=col(0.9, 0, (0.8, 0.66, 0.48))[:3], profile=lambda t: 1.0)
        o = len(vs)
        vs += [tuple(v) for v in v_]
        cs += [(*c[:3], 0.5 * c[3]) for c in c_]
        fs += [tuple(o + i for i in f) for f in f_]
        for rr, dz, sh in ((0.014, 0.0, 1.0),) if lo else ((0.008, 0.0, 1.0), (0.016, -0.006, 0.85)):     # венчики щупалец
            o = len(vs)
            vs.append(tuple(tip + Vector((0, 0, 0.004 + dz))))
            cs.append(col(sh, 0.8, (1.0, 0.45, 0.55)))
            for i in range(5):
                q = 2 * math.pi * i / 5
                vs.append(tuple(tip + Vector((rr * math.cos(q), rr * math.sin(q), dz))))
                cs.append(col(sh, 0.8, (1.0, 0.5, 0.6)))
            fs += [(o, o + 1 + i, o + 1 + (i + 1) % 5) for i in range(5)]
    return vs, fs, cs


def g_alcyonium(rng, lo=False):
    """Alcyonium digitatum («пальцы мертвеца»): 5 толстых пальцев 7-14 см от общей подошвы."""
    vs, cs, fs = [], [], []
    seg = 4 if lo else 6
    nf = 3 if lo else 5
    for k in range(nf):
        q0 = 2 * math.pi * k / nf + rng.uniform(-0.3, 0.3)
        lean = Vector((math.cos(q0), math.sin(q0), 0)) * rng.uniform(0.25, 0.6)
        L = rng.uniform(0.07, 0.14)
        base = Vector((0.02 * math.cos(q0), 0.02 * math.sin(q0), 0))
        o = len(vs)
        for t in (0.0, 0.35, 0.7, 1.0):
            cpt = base + (Vector((0, 0, 1)) + lean * t) * (L * t)
            r = 0.022 * (1 - 0.3 * t)
            for i in range(seg):
                q = 2 * math.pi * i / seg
                vs.append(tuple(cpt + Vector((r * math.cos(q), r * math.sin(q), 0))))
                cs.append(col(0.75 + 0.3 * t, 0.15 * t))
        for t_i in range(3):
            fs += ring_faces(o + t_i * seg, o + (t_i + 1) * seg, seg)
        tipc = base + (Vector((0, 0, 1)) + lean) * L + Vector((0, 0, 0.012))
        vs.append(tuple(tipc))
        cs.append(col(1.05, 0.15))
        fs += [(len(vs) - 1, o + 3 * seg + i, o + 3 * seg + (i + 1) % seg) for i in range(seg)]
    return vs, fs, cs


def g_blob(rng, r=0.06, flat=0.6, bumps=0.25, sub=2):
    """Комок (губка): икосфера с буграми, приплюснутая, низ срезан по подошве."""
    bm_ = bmesh.new()
    bmesh.ops.create_icosphere(bm_, subdivisions=sub, radius=1.0)
    dirs = [Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(0, 1))).normalized() for _ in range(6)]
    vs, cs = [], []
    for v in bm_.verts:
        d = v.co.normalized()
        k = 1 + bumps * sum(max(d.dot(q), 0) ** 4 for q in dirs) - 0.05 * rng.random()
        p_ = d * k * r
        p_.z = max(p_.z * flat + r * flat * 0.3, 0.0)
        vs.append(tuple(p_))
        cs.append(col(0.7 + 0.4 * max(d.z, 0), 0.0))
    fs = [tuple(v.index for v in f.verts) for f in bm_.faces]
    bm_.free()
    return vs, fs, cs


def g_mussels(rng, lo=False):
    """Мидии Mytilus edulis: гроздь из 9 раковин 3-6 см, торчат в разные стороны."""
    vs, cs, fs = [], [], []
    sides = 4 if lo else 6
    for _ in range(4 if lo else 9):
        L = rng.uniform(0.03, 0.06)
        ax = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(0.4, 1.5))).normalized()
        M = frame(ax, rng.uniform(0, 6.28))
        base = Vector((rng.uniform(-0.03, 0.03), rng.uniform(-0.03, 0.03), 0))
        o = len(vs)
        for t in (0.0, 0.33, 0.7, 1.0):
            w = L * 0.28 * math.sin(math.pi * min(t * 0.9 + 0.08, 1.0))
            for i in range(sides):
                q = 2 * math.pi * i / sides
                vs.append(tuple(base + M @ Vector((w * math.cos(q), 0.6 * w * math.sin(q), L * t))))
                cs.append(col(0.8 + 0.4 * (i in (1, 2)), 0.0))
        for k in range(3):
            fs += ring_faces(o + k * sides, o + (k + 1) * sides, sides)
    return vs, fs, cs


def g_urchin(rng, lo=False):
    """Морской ёж Echinus esculentus: панцирь ∅ 10 см, приплюснут, короткие иглы (пирамидки на гранях)."""
    bm_ = bmesh.new()
    bmesh.ops.create_icosphere(bm_, subdivisions=1, radius=0.05)
    for v in bm_.verts:
        v.co.z = v.co.z * 0.85 + 0.042
    bm_.normal_update()
    vs = [tuple(v.co) for v in bm_.verts]
    cs = [col(0.9, 0.0) for _ in vs]
    fs = []
    for f in bm_.faces:
        ids = [v.index for v in f.verts]
        if lo:                                     # без игл
            fs.append(tuple(ids))
            continue
        tip = f.calc_center_median() + f.normal * 0.012
        o = len(vs)
        vs.append(tuple(tip))
        cs.append(col(1.25, 0.0, (1.0, 0.85, 0.85)))
        for a_, b2 in ((ids[0], ids[1]), (ids[1], ids[2]), (ids[2], ids[0])):
            fs.append((a_, b2, o))
    bm_.free()
    return vs, fs, cs


def g_star(n_arm, R, valley, ring_rgb=None):
    """Морская звезда: n_arm лучей длиной R, спина приподнята; ring_rgb — светлое кольцо на диске (солнечник)."""
    m2 = 2 * n_arm
    vs = [(0, 0, 0.22 * R), (0, 0, 0.005)]
    cs = [col(1.0, 0.0, ring_rgb or (1, 1, 1)), col(0.7, 0.0)]
    for i in range(m2):
        q = 2 * math.pi * i / m2
        rr = R if i % 2 == 0 else valley * R
        vs.append((rr * math.cos(q), rr * math.sin(q), 0.08 * R if i % 2 == 0 else 0.1 * R))
        cs.append(col(1.0 if i % 2 == 0 else 0.9, 0.0))
    fs = [(1, 2 + (i + 1) % m2, 2 + i) for i in range(m2)]            # низ
    o = len(vs)
    for i in range(m2):                                               # кольцо диска на 0,35 R
        q = 2 * math.pi * i / m2
        vs.append((0.35 * R * math.cos(q), 0.35 * R * math.sin(q), 0.18 * R))
        cs.append(col(1.0, 0.0, ring_rgb or (1, 1, 1)))
    fs += [(0, o + i, o + (i + 1) % m2) for i in range(m2)]
    fs += [(o + i, 2 + i, 2 + (i + 1) % m2, o + (i + 1) % m2) for i in range(m2)]
    return vs, fs, cs


def g_brittle(rng, lo=False):
    """Офиура Ophiura: диск ∅ 1,6 см и 5 тонких изогнутых лучей по 6 см (плоские ленты)."""
    vs, cs, fs = [(0, 0, 0.004)], [col(1.0, 0.0)], []
    for i in range(6):
        q = 2 * math.pi * i / 6
        vs.append((0.008 * math.cos(q), 0.008 * math.sin(q), 0.002))
        cs.append(col(0.9, 0.0))
    fs += [(0, 1 + i, 1 + (i + 1) % 6) for i in range(6)]
    for k in range(5):
        q = 2 * math.pi * k / 5
        bend = rng.uniform(-0.6, 0.6)
        pts = []
        ts = (0.0, 0.5, 1.0) if lo else (0.0, 0.33, 0.66, 1.0)
        for t in ts:
            a = q + bend * t * t
            pts.append((0.007 + 0.055 * t) * Vector((math.cos(a), math.sin(a), 0)) + Vector((0, 0, 0.002 + 0.004 * t * (1 - t))))
        o = len(vs)
        nl = len(pts) - 1
        for j, pt in enumerate(pts):
            dirv = (pts[min(j + 1, nl)] - pts[max(j - 1, 0)]).normalized()
            sd = Vector((-dirv.y, dirv.x, 0)) * 0.0022 * (1 - 0.6 * j / nl)
            vs += [tuple(pt - sd), tuple(pt + sd)]
            cs += [col(0.85, 0.0), col(0.85, 0.0)]
        fs += [(o + 2 * j, o + 2 * j + 1, o + 2 * j + 3, o + 2 * j + 2) for j in range(nl)]
    return vs, fs, cs


def _merge(parts):
    vs, fs, cs = [], [], []
    for v_, f_, c_ in parts:
        o = len(vs)
        vs += [tuple(v) for v in v_]
        fs += [tuple(o + i for i in f) for f in f_]
        cs += list(c_)
    return vs, fs, cs


def g_kelp_digitata(rng, lo=False):
    """Ламинария пальчаторассечённая: стволик 30 см, пластина рассечена на 6 ремней по 0,5-0,9 м, ложатся по +x."""
    v_, f_, c_ = ribbon((0, 0, 0), (0.1, 0, 1), (0, 0, 0), 0.3, 0.018, 3, Vector((0, 1, 0)), across=2,
                        tone=col(0.8, 0)[:3], profile=lambda t: 1.0, sway_pow=2.0)
    parts = [(v_, f_, [(*c[:3], 0.15 * c[3]) for c in c_])]
    top = Vector((0.03, 0, 0.3))
    nst = 3 if lo else 6
    for k in range(nst):
        sp_ = (k - (nst - 1) / 2) / ((nst - 1) / 2)
        v_, f_, c_ = ribbon(top, Vector((0.5, sp_ * 0.5, 0.9)), Vector((0.6, sp_ * 0.35, -0.5)), rng.uniform(0.5, 0.9),
                            rng.uniform(0.035, 0.05) * (1.6 if lo else 1.0), 4 if lo else 8, Vector((-sp_, 1, 0)),
                            ruffle=0.0 if lo else 0.01, across=2 if lo else 3, tone=col(rng.uniform(0.85, 1.1), 0)[:3],
                            profile=lambda t: 0.7 + 0.3 * math.sin(math.pi * min(t * 1.3, 1)), sway_pow=1.2)
        parts.append((v_, f_, [(*c[:3], 0.15 + 0.85 * c[3]) for c in c_]))
    return _merge(parts)


def g_kelp_sacch(rng, lo=False):
    """Сахарина Saccharina latissima: короткий стволик и одна волнистая пластина 1,1 м × 15 см по +x."""
    prof = lambda t: 0.12 if t < 0.12 else 0.35 + 0.65 * math.sin(math.pi * min((t - 0.12) / 0.92, 1.0)) ** 0.5
    return _merge([ribbon((0, 0, 0), (0.3, 0, 1), (0.75, 0.0, -0.55), 1.1, 0.15, 6 if lo else 14, Vector((0, 1, 0)),
                          ruffle=0.0 if lo else 0.03, across=2 if lo else 3, profile=prof, tone=col(1.0, 0)[:3], sway_pow=1.2)])


def g_redalgae(rng, lo=False):
    """Красные водоросли (Delesseria, Phycodrys): веер из 6 тонких листьев 8-16 см."""
    parts = []
    nb = 3 if lo else 6
    for k in range(nb):
        q = 2 * math.pi * k / nb + rng.uniform(-0.4, 0.4)
        parts.append(ribbon((0, 0, 0), Vector((0.5 * math.cos(q), 0.5 * math.sin(q), 1.0)), Vector((0.25, 0, -0.2)),
                            rng.uniform(0.08, 0.16), rng.uniform(0.035, 0.05) * (1.4 if lo else 1.0), 2 if lo else 4,
                            Vector((-math.sin(q), math.cos(q), 0)), ruffle=0.0 if lo else 0.006, across=2 if lo else 3,
                            tone=col(rng.uniform(0.8, 1.15), 0)[:3],
                            profile=lambda t: 0.3 + 0.7 * math.sin(math.pi * min(t * 1.1, 1.0))))
    return _merge(parts)


lr = random.Random(55)
M_METR = plain_mat("BIO_metridium", (0.60, 0.57, 0.50), 0.7)
M_HYDR = plain_mat("BIO_hydroid", (0.55, 0.50, 0.45), 0.7)
M_ALCY = plain_mat("BIO_alcyonium", (0.60, 0.55, 0.47), 0.7)
M_SPON = plain_mat("BIO_sponge", (0.52, 0.38, 0.10), 0.8)
M_MUSS = plain_mat("BIO_mussel", (0.035, 0.04, 0.06), 0.4)
M_URCH = plain_mat("BIO_urchin", (0.42, 0.20, 0.22), 0.8)
M_STAR = plain_mat("BIO_starfish", (0.50, 0.16, 0.06), 0.8)
M_BRIT = plain_mat("BIO_brittle", (0.30, 0.27, 0.22), 0.8)
M_KELP = plain_mat("BIO_kelp", (0.085, 0.065, 0.022), 0.7)
M_RED = plain_mat("BIO_redalgae", (0.25, 0.045, 0.05), 0.8)
lo_r = random.Random(56)
make_proto("metridium", M_METR, g_metridium(), g_metridium(True))
make_proto("hydroid", M_HYDR, g_hydroid(lr), g_hydroid(lo_r, True))
make_proto("alcyonium", M_ALCY, g_alcyonium(lr), g_alcyonium(lo_r, True))
make_proto("sponge", M_SPON, g_blob(lr, 0.06, 0.55, 0.3, sub=1))
make_proto("mussels", M_MUSS, g_mussels(lr), g_mussels(lo_r, True))
make_proto("urchin", M_URCH, g_urchin(lr), g_urchin(lo_r, True))
make_proto("asterias", M_STAR, g_star(5, 0.09, 0.3))
make_proto("sunstar", M_STAR, g_star(11, 0.1, 0.5, ring_rgb=(1.0, 0.8, 0.7)))
make_proto("brittle", M_BRIT, g_brittle(lr), g_brittle(lo_r, True))
make_proto("kelp_dig", M_KELP, g_kelp_digitata(lr), g_kelp_digitata(lo_r, True))
make_proto("kelp_sac", M_KELP, g_kelp_sacch(lr), g_kelp_sacch(lo_r, True))
make_proto("redalgae", M_RED, g_redalgae(lr), g_redalgae(lo_r, True))


def inst(sp, p, R, scale, tone):
    INST.setdefault(sp, []).append((Vector(p), R @ Matrix.Diagonal((scale, scale, scale)), tone))


# точки корпуса: многоугольники скана (центр, нормаль, площадь, высота над илом); «лист» — не леер
R3 = ship_m.to_3x3()
polys = []
for poly in hull.data.polygons:
    cw = ship_m @ poly.center
    if abs(cw.x) > 15 or abs(cw.y) > 15:
        continue
    hz = cw.z - ground(cw.x, cw.y)
    if hz < 0.04:
        continue
    polys.append((cw, (R3 @ poly.normal).normalized(), poly.area, hz))
kd_all = kdtree.KDTree(len(polys))
for i, pp in enumerate(polys):
    kd_all.insert(pp[0], i)
kd_all.balance()


def is_plate(p_):
    """Лист или леер: окрестность 15 см вытянута в линию (леер, труба) или плоская (лист обшивки, палуба)."""
    pts = np.array([q[0] for q in kd_all.find_range(p_, 0.15)])
    if len(pts) < 5:
        return False
    ev = np.sort(np.linalg.eigvalsh(np.cov((pts - pts.mean(0)).T)))
    return ev[1] > 0.2 * ev[2]


plate = [is_plate(pp[0]) for pp in polys]
log("корпус: граней над илом", len(polys), "на листах", sum(plate))


class Spacing:
    """Не ставить два экземпляра в одну ячейку d × d × d (хеш по сетке)."""
    def __init__(self, d):
        self.d, self.cells = d, set()

    def ok(self, p):
        key = (round(p.x / self.d), round(p.y / self.d), round(p.z / self.d))
        if key in self.cells:
            return False
        self.cells.add(key)
        return True


def pick(cond, n, rng):
    """n случайных граней корпуса с условием cond(i), вероятность ∝ площади."""
    ids = [i for i in range(len(polys)) if cond(i)]
    if not ids:
        return []
    return rng.choices(ids, weights=[polys[i][2] for i in ids], k=n)


def tone_jit(rng, base, amt=0.12):
    return tuple(max(0.0, b_ * rng.uniform(1 - amt, 1 + amt)) for b_ in base)


def along_ship(p):
    return p.x * s + p.y * c


METR_MORPH = [(1.0, 1.0, 0.97), (1.0, 1.0, 0.97), (1.0, 0.75, 0.55), (1.0, 0.55, 0.25), (0.95, 0.85, 0.75)]  # белые, персиковые, оранжевые
STAR_TONES = [(1, 1, 1), (1, 1.4, 1.3), (0.8, 0.6, 1.0)]
sp_m = Spacing(0.075)
# Metridium: «ковры» на бортах и стенках рубки (вертикальные листы): пятна 0,3-1 м, плотно
for sd in pick(lambda i: plate[i] and abs(polys[i][1].z) < 0.55 and polys[i][3] < 2.6, 70, lr):
    morph = lr.choice(METR_MORPH)
    near_ids = kd_all.find_range(polys[sd][0], lr.uniform(0.3, 1.0))
    lr.shuffle(near_ids)
    for co, i, dd in near_ids[:lr.randint(15, 45)]:
        cw, nw, ar, hz = polys[i]
        if abs(nw.z) < 0.7 and sp_m.ok(cw):
            inst("metridium", cw, frame((nw + Vector((0, 0, 0.35))).normalized(), lr.uniform(0, 6.28)), lr.uniform(0.55, 1.5),
                 tone_jit(lr, morph, 0.06))
# одиночные актинии по всему корпусу
for i in pick(lambda i: polys[i][3] < 3.0, 500, lr):
    cw, nw, ar, hz = polys[i]
    if sp_m.ok(cw):
        inst("metridium", cw, frame((nw + Vector((0, 0, 0.5))).normalized(), lr.uniform(0, 6.28)), lr.uniform(0.4, 1.0),
             tone_jit(lr, lr.choice(METR_MORPH), 0.06))
# гидроиды Tubularia: на леерах, кромках и верхних гранях
sp_h = Spacing(0.06)
for i in pick(lambda i: (not plate[i]) or polys[i][1].z > 0.4, 700, lr):
    cw, nw, ar, hz = polys[i]
    if sp_h.ok(cw):
        inst("hydroid", cw, frame((nw + Vector((0, 0, 0.8))).normalized(), lr.uniform(0, 6.28)), lr.uniform(0.7, 1.4),
             tone_jit(lr, (1, 1, 1), 0.1))
# «пальцы мертвеца» у носа и кормы (там сильнее течение), белые и оранжевые
for i in pick(lambda i: plate[i] and abs(along_ship(polys[i][0])) > 2.5 and polys[i][1].z < 0.6, 160, lr):
    cw, nw, ar, hz = polys[i]
    if sp_m.ok(cw):
        inst("alcyonium", cw, frame((nw + Vector((0, 0, 0.3))).normalized(), lr.uniform(0, 6.28)), lr.uniform(0.7, 1.4),
             tone_jit(lr, lr.choice([(1, 1, 0.95), (1, 0.6, 0.3), (1, 0.75, 0.5)]), 0.05))
# губки, мидии, ежи, звёзды
for i in pick(lambda i: plate[i] and polys[i][3] < 1.6, 220, lr):
    cw, nw, ar, hz = polys[i]
    if sp_m.ok(cw):
        inst("sponge", cw, frame(nw, lr.uniform(0, 6.28)), lr.uniform(0.5, 1.6),
             tone_jit(lr, lr.choice([(1, 1, 1), (1.1, 0.9, 0.6), (0.9, 0.7, 0.9)]), 0.08))
for i in pick(lambda i: polys[i][1].z > 0.2 and polys[i][3] > 0.8, 260, lr):
    cw, nw, ar, hz = polys[i]
    if sp_m.ok(cw):
        inst("mussels", cw, frame(nw, lr.uniform(0, 6.28)), lr.uniform(0.8, 1.5), tone_jit(lr, (1, 1, 1), 0.15))
for i in pick(lambda i: plate[i] and polys[i][1].z > -0.2, 90, lr):
    cw, nw, ar, hz = polys[i]
    if sp_m.ok(cw):
        inst("urchin", cw, frame(nw, lr.uniform(0, 6.28)), lr.uniform(0.7, 1.3), tone_jit(lr, (1, 1, 1), 0.12))
for i in pick(lambda i: plate[i], 70, lr):
    cw, nw, ar, hz = polys[i]
    sp = "sunstar" if lr.random() < 0.3 else "asterias"
    inst(sp, cw + nw * 0.005, frame(nw, lr.uniform(0, 6.28)), lr.uniform(0.7, 1.3),
         tone_jit(lr, (1, 1, 1) if sp == "sunstar" else lr.choice(STAR_TONES), 0.1))
# водоросли: ламинария на палубе, крыше рубки и стреле (верхние листы выше 1 м), красные — по верхним граням
sp_k = Spacing(0.18)
for i in pick(lambda i: plate[i] and polys[i][1].z > 0.7 and polys[i][3] > 1.0, 160, lr):
    cw, nw, ar, hz = polys[i]
    if sp_k.ok(cw):
        inst("kelp_dig" if lr.random() < 0.5 else "kelp_sac", cw,
             frame_dir((nw + Vector((0, 0, 1.0))).normalized(), CURRENT, 0.5, lr), lr.uniform(0.7, 1.3), tone_jit(lr, (1, 1, 1), 0.15))
for i in pick(lambda i: polys[i][1].z > 0.3, 420, lr):
    cw, nw, ar, hz = polys[i]
    if sp_h.ok(cw):
        inst("redalgae", cw, frame_dir(nw, CURRENT, 1.2, lr), lr.uniform(0.6, 1.4), tone_jit(lr, (1, 1, 1), 0.2))


def surface_points(o, n, rng, zmin=0.3):
    """Точки на поверхности предмета o (лучи снаружи к центру); только грани с нормалью z > −zmin."""
    mw = o.matrix_world
    mi = mw.inverted()
    nmat = mw.to_3x3().inverted().transposed()
    ctr = mw @ (sum((Vector(v) for v in o.bound_box), Vector()) / 8)
    rad = max(o.dimensions) * 0.75 + 0.3
    out = []
    for _ in range(n * 6):
        d = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-0.2, 1))).normalized()
        ok, p_, nr, _i = o.ray_cast(mi @ (ctr + d * rad), mi.to_3x3() @ (-d))
        if ok:
            pw, nw = mw @ p_, (nmat @ nr).normalized()
            if nw.z > -zmin and pw.z > ground(pw.x, pw.y) + 0.03:
                out.append((pw, nw))
        if len(out) >= n:
            break
    return out


# на обломках, бочках, якоре и валунах — те же виды, реже
bpy.context.view_layer.update()
hard = props + [anc] + [o for o in bpy.data.objects if o.name.startswith("Debris_")]
for o in hard:
    for pw, nw in surface_points(o, 18, lr):
        r_ = lr.random()
        if r_ < 0.45:
            inst("metridium", pw, frame((nw + Vector((0, 0, 0.4))).normalized(), lr.uniform(0, 6.28)), lr.uniform(0.4, 1.1),
                 tone_jit(lr, lr.choice(METR_MORPH), 0.06))
        elif r_ < 0.7:
            inst("hydroid", pw, frame((nw + Vector((0, 0, 0.8))).normalized(), lr.uniform(0, 6.28)), lr.uniform(0.6, 1.2),
                 tone_jit(lr, (1, 1, 1), 0.1))
        elif r_ < 0.85:
            inst("redalgae", pw, frame_dir(nw, CURRENT, 1.2, lr), lr.uniform(0.5, 1.2), tone_jit(lr, (1, 1, 1), 0.2))
        else:
            inst("sponge", pw, frame(nw, lr.uniform(0, 6.28)), lr.uniform(0.4, 1.0), tone_jit(lr, (1, 1, 1), 0.1))
for o in rocks:
    big = max(o.dimensions) > 0.9
    for pw, nw in surface_points(o, 30 if big else 8, lr, zmin=-0.2):
        r_ = lr.random()
        if big and nw.z > 0.6 and r_ < 0.35:
            inst(lr.choice(["kelp_dig", "kelp_sac"]), pw, frame_dir((nw + Vector((0, 0, 1))).normalized(), CURRENT, 0.5, lr),
                 lr.uniform(0.7, 1.2), tone_jit(lr, (1, 1, 1), 0.15))
        elif r_ < 0.6:
            inst("redalgae", pw, frame_dir(nw, CURRENT, 1.2, lr), lr.uniform(0.5, 1.3), tone_jit(lr, (1, 1, 1), 0.2))
        elif r_ < 0.8:
            inst("metridium", pw, frame((nw + Vector((0, 0, 0.4))).normalized(), lr.uniform(0, 6.28)), lr.uniform(0.4, 1.0),
                 tone_jit(lr, lr.choice(METR_MORPH), 0.06))
        else:
            inst("urchin", pw, frame(nw, lr.uniform(0, 6.28)), lr.uniform(0.7, 1.2), tone_jit(lr, (1, 1, 1), 0.12))
# на иле: офиуры гуще всего у корпуса (детрит), звёзды, солнечники
n_br = 0
while n_br < 1600:
    x, y = lr.uniform(-12, 12), lr.uniform(-12, 12)
    tb, sv, dd = ground_cell(x, y)
    if dd > 0.15 and lr.random() < math.exp(-dd / 2.2):
        inst("brittle", (x, y, ground(x, y) + 0.003), frame(ground_n(x, y), lr.uniform(0, 6.28)), lr.uniform(0.7, 1.3),
             tone_jit(lr, (1, 1, 1), 0.2))
        n_br += 1
n_st = 0
while n_st < 60:
    x, y = lr.uniform(-10, 10), lr.uniform(-10, 10)
    if 0.3 < ground_cell(x, y)[2] < 6.0:
        sp = "sunstar" if lr.random() < 0.25 else "asterias"
        inst(sp, (x, y, ground(x, y) + 0.004), frame(ground_n(x, y), lr.uniform(0, 6.28)), lr.uniform(0.7, 1.3),
             tone_jit(lr, (1, 1, 1) if sp == "sunstar" else lr.choice(STAR_TONES), 0.1))
        n_st += 1
log("экземпляры", {k: len(v) for k, v in INST.items()}, "всего", sum(len(v) for v in INST.values()))

LIFE_JSON = ROOT + "/godot/assets/wreck/wreck_life.json"
LIFE_CELL = 3.0      # ячейки экземпляров в Godot: мельче, чем у мелочи, — по ним же выбирается уровень детализации


def export_life():
    """Экземпляры в осях Godot (glTF: x, z, −y) относительно корня сцены места: строка = положение (3),
    столбцы базиса с масштабом (9), тон (3)."""
    C = Matrix(((1, 0, 0), (0, 0, 1), (0, -1, 0)))
    out = {"cell": LIFE_CELL, "species": {}}
    for sp, lst in INST.items():
        rows = []
        for p_, R, tone in lst:
            Rg = C @ R @ C.transposed()
            rows.append([round(p_.x, 4), round(p_.z, 4), round(-p_.y, 4)]
                        + [round(Rg[i][j], 4) for j in range(3) for i in range(3)] + [round(t, 3) for t in tone])
        out["species"][sp] = rows
    json.dump(out, open(LIFE_JSON, "w", encoding="utf-8"), separators=(",", ":"))
    log("wreck_life.json", os.path.getsize(LIFE_JSON) // 1024, "КБ")


export_life()

# дома подвижной живности (Godot: game/fauna.gd): треска парит у корпуса, камбала лежит на иле, крабы ходят у дна
def home(name, u, v, h):
    p = fwd * u + side * v
    e = bpy.data.objects.new(name, None)
    coll.objects.link(e)
    e.location = (p.x, p.y, ground(p.x, p.y) + h)


for k, (u, v, h) in enumerate(((-3.0, -HALF_B - 1.4, 0.9), (2.0, -HALF_B - 1.2, 1.2), (-0.5, HALF_B + 1.0, 0.8),
                               (-HALF_L - 1.6, 0.0, 1.0), (3.5, HALF_B + 1.3, 1.3), (HALF_L + 1.2, 0.8, 0.9),
                               (-4.5, HALF_B + 1.2, 0.7), (0.5, -HALF_B - 2.4, 1.6))):
    home("Home_cod_%d" % k, u, v, h)
for k, (u, v, h) in enumerate(((1.0, HALF_B + 0.6, 0.6), (-2.0, -HALF_B - 0.6, 0.7), (4.2, -HALF_B - 0.5, 0.8),
                               (-3.6, HALF_B + 0.7, 0.5))):
    home("Home_wrasse_%d" % k, u, v, h)
for k, (u, v) in enumerate(((4.0, -6.0), (-3.5, 6.5), (6.5, 3.0), (-7.5, -4.0), (8.5, -2.5))):
    home("Home_flounder_%d" % k, u, v, 0.0)
for k, (u, v) in enumerate(((-1.0, 3.0), (2.5, -3.6), (-5.5, -2.0), (7.0, 0.5), (0.5, 3.3), (-3.0, -3.5),
                            (5.2, 3.4), (-6.4, 2.2), (3.6, -3.1), (-1.8, -4.2))):
    home("Home_crab_%d" % k, u, v, 0.0)
# ось судна для стай, что обходят корпус (Godot: game/fauna.gd)
home("ShipStern", -HALF_L, 0.0, 0.0)
home("ShipBow", HALF_L, 0.0, 0.0)

# ---------------- точки осмотра (по деталям скана, координаты судна: нос +Y, правый борт +X) ----------------
def ip(name, p_ship=None, p_world=None):
    e = bpy.data.objects.new(name, None)
    coll.objects.link(e)
    e.location = world_of_ship(p_ship) if p_ship is not None else p_world
    return e


def hull_point(end, z, fallback):
    """Точка на поверхности скана у носа (end = +1) или кормы (−1) на высоте z (оси скана = оси судна), 8 см снаружи."""
    for zz in (z, z - 0.3, z + 0.3, z - 0.5):
        for x in (-0.3, -0.6, 0.0, 0.3):
            ok, p_, n_, _i = hull.ray_cast(Vector((x, 8.0 * end, zz)), Vector((0.0, -float(end), 0.0)))
            if ok and p_.y * end > 2.8:              # сам торец, а не рубка за открытой кормой
                return tuple(p_ + n_.normalized() * 0.08)
    return fallback


IPS = [
    ip("IP_1_нос и форштевень", hull_point(+1, 1.4, (0.0, 4.6, 1.3))),
    ip("IP_2_рубка окна и дверь", (-1.95, 0.3, 2.2)),          # снаружи левой стенки рубки и лееров (x ≈ −1,8 м)
    ip("IP_3_стрела на крыше рубки", (0.0, 0.5, 3.85)),
    ip("IP_4_корма", hull_point(-1, 1.5, (0.0, -4.8, 1.4))),
    ip("IP_5_якорь и цепь", None, Vector((anchor_xy.x, anchor_xy.y, az + 0.3))),
    ip("IP_6_бочки у правого борта", None, Vector(props[0].location) + Vector((0, 0, 0.3))),
]

# ---------------- экспорт ----------------
bpy.context.view_layer.update()
tris = {o.name: sum(len(p.vertices) - 2 for p in o.data.polygons) for o in coll.objects if o.type == "MESH"}
total = sum(tris.values())
rep = {"tris_total": total, "tris_seabed": tris["Seabed"], "tris_hull": tris["WreckHull"],
       "heading": HEADING, "heel": HEEL, "trim": TRIM, "sink": SINK,
       "inspection_points": {e.name: [round(v, 3) for v in e.location] for e in IPS}}
json.dump(rep, open(REPORT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
log(json.dumps(rep, ensure_ascii=False))
bpy.ops.wm.save_as_mainfile(filepath=ROOT + "/blender/wreck_site.blend")


def export_glb():
    """Экспорт в Godot. Картинки материалов MAT_* (наборы Poly Haven) не встраиваются: Godot берёт их из
    godot/assets/textures по имени материала; встраивается только фото-текстура скана."""
    for m in bpy.data.materials:
        if m.name.startswith("MAT_") and m.use_nodes:
            for n in [n for n in m.node_tree.nodes if n.type in ("TEX_IMAGE", "VERTEX_COLOR")]:
                m.node_tree.nodes.remove(n)       # с узлом цвета вершин экспортёр пишет цвет без альфы (маски)
    small = bpy.data.images.load(ROOT + "/godot/assets/wreck/malpas_basecolor.jpg", check_existing=False)
    small.name = "malpas_basecolor_4k"
    for m in hull.data.materials:                  # в .blend скана упакован исходник 8192²: подставить 4096²
        for n in m.node_tree.nodes:
            if n.type == "TEX_IMAGE":
                n.image = small
    os.makedirs(os.path.dirname(GLB), exist_ok=True)
    for me_ in bpy.data.meshes:                    # цвет вершин с альфой (маски гравия, ржавчины): экспортёр glTF
        if not me_.color_attributes:               # теряет альфу у байтового атрибута — переводим во float
            continue
        src = me_.color_attributes[0]
        if src.data_type == "BYTE_COLOR":
            vals = [0.0] * (len(src.data) * 4)
            src.data.foreach_get("color", vals)
            dom, nm = src.domain, src.name
            me_.color_attributes.remove(src)
            dst = me_.color_attributes.new(nm, "FLOAT_COLOR", dom)
            dst.data.foreach_set("color", vals)
        nm = me_.color_attributes[0].name
        me_.color_attributes.active_color_name = nm
        me_.color_attributes.default_color_name = nm
    for o in bpy.context.view_layer.objects:
        o.select_set(o.users_collection[0] == coll and o.type in ("MESH", "EMPTY"))
    bpy.ops.export_scene.gltf(filepath=GLB, export_format="GLB", export_copyright="ROV-Sim, Kholopov E. G. (Холопов Е. Г.), 2026, CC BY 4.0; wreck scan: Malpas Metal Boat Wreck by artfletch, CC BY 4.0",  # то же пишет work/tools/stamp_glb.py
        use_selection=True, export_apply=True,
                              export_yup=True, export_attributes=True, export_vertex_color="ACTIVE",
                              export_image_format="JPEG", export_image_quality=88)
    log("glb", os.path.getsize(GLB) // 1024, "КБ")

# ---------------- сухие рендеры ----------------
if render_dir:
    os.makedirs(render_dir, exist_ok=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 48
    sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = 1280, 720
    sc.view_settings.view_transform = "AgX"
    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.6, 0.62, 0.66, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.5
    sc.world = world
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 3.0
    sun.rotation_euler = (math.radians(45), 0, math.radians(20))
    coll.objects.link(sun)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.lens = 28
    coll.objects.link(cam)
    sc.camera = cam
    # экземпляры обрастания — связанные копии образцов (только для рендера, в glb не попадают)
    rcoll = bpy.data.collections.new("render_inst")
    sc.collection.children.link(rcoll)
    for sp_, lst in INST.items():
        for k_, (p_, R, tone) in enumerate(lst):
            o = bpy.data.objects.new("ri_%s_%d" % (sp_, k_), PROTOS[sp_].data)
            o.matrix_world = Matrix.Translation(p_) @ R.to_4x4()
            rcoll.objects.link(o)
    m0 = max(INST["metridium"], key=lambda r_: len([q for q in INST["metridium"] if (q[0] - r_[0]).length < 0.5]))[0]
    m_out = Vector((m0.x, m0.y, 0)).normalized()
    br = next(r_[0] for r_ in INST["brittle"] if ground_cell(r_[0].x, r_[0].y)[2] < 0.6)
    views = [((11, -9, 5.5), (0, 0, 1.0)), ((-10, 8, 4.0), (0, 0, 1.0)), ((0, 0, 16), (0, 0.01, 0)),
             (tuple(bow_tip + fwd * 6 + Vector((-c * 3, s * 3, 2.5))), tuple(anchor_xy * 0.5 + bow_tip * 0.5)),
             ((6, 3, 2.0), (0, 0, 1.2)), ((-4.5, -6, 1.6), (0, -2, 1.0)),
             (tuple(Vector(anc.location) + Vector((1.6, -1.2, 1.1))), tuple(anc.location)),          # якорь
             (tuple(world_of_ship((-4.5, 1.0, 1.2))), tuple(world_of_ship((-1.6, 0.0, 0.6)))),     # нанос у левого борта
             (tuple(Vector(props[0].location) + Vector((-1.6, -1.3, 0.9)) - side * 0.8), tuple(Vector(props[0].location) + side * 0.6)),
             (tuple(m0 + m_out * 1.1 + Vector((0, 0, 0.3))), tuple(m0)),                         # ковёр актиний
             (tuple(world_of_ship((1.5, 2.0, 4.8))), tuple(world_of_ship((0.0, 0.3, 3.0)))),        # ламинария на рубке
             (tuple(bow_tip + fwd * 2.5 + Vector((0, 0, 1.6))), tuple(bow_tip + fwd * 0.6 + Vector((0, 0, -0.6)))),   # яма размыва у носа
             (tuple(br + Vector((0.5, -0.6, 0.6))), tuple(br)),                                     # офиуры у борта
             ((15.0, -15.0, 2.5), (30.0, -30.0, 0.0))]                                              # к краю: дно без обрыва
    for k, (loc, tgt) in enumerate(views):
        cam.location = loc
        cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = f"{render_dir}/site_{k}.png"
        bpy.ops.render.render(write_still=True)
        log("рендер", sc.render.filepath)

export_glb()   # после рендеров: узлы картинок MAT_* удаляются
