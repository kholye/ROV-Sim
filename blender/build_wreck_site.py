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
 - якорь Холла на дне перед носом, цепь от клюза частично в иле; 2 бочки, ящик, покрышка, камни.
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
from mathutils import Euler, Matrix, Vector

ROOT = "D:/Документы/ROV-Sim"
SCAN = ROOT + "/blender/wreck_scan.blend"
GLB = ROOT + "/godot/assets/wreck/wreck_site.glb"
REPORT = ROOT + "/blender/wreck_site_report.json"
TEX = ROOT + "/godot/assets/textures"

SIZE = 40.0
RES = 0.4                     # шаг сетки дна, м
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


M_SEABED = tex_mat("MAT_brown_mud_02__dense_sand", "brown_mud_02", 1.0, "dense_sand")
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
rng = np.random.default_rng(1904)
n = int(SIZE / RES) + 1
xs = np.linspace(-SIZE / 2, SIZE / 2, n)
X, Y = np.meshgrid(xs, xs, indexing="xy")


def value_noise(X, Y, scale, seed):
    """Гладкий шум: сумма синусоид со случайными направлениями (детерминированно)."""
    r = np.random.default_rng(seed)
    h = np.zeros_like(X)
    for _ in range(6):
        a = r.uniform(0, 2 * np.pi)
        k = 2 * np.pi / (scale * r.uniform(0.7, 1.4))
        h += np.sin(k * (X * np.cos(a) + Y * np.sin(a)) + r.uniform(0, 2 * np.pi))
    return h / 6


Rr = np.hypot(X, Y)
H = 0.30 * value_noise(X, Y, 9.0, 1) + 0.08 * value_noise(X, Y, 3.0, 2)
H += np.clip((Rr - 14.0) / 6.0, 0, 1) ** 2 * (0.8 + 1.2 * value_noise(X, Y, 7.0, 3))   # холмы дальше 14 м
# координаты в осях судна (без учёта крена: только курс)
c, s = math.cos(math.radians(HEADING)), math.sin(math.radians(HEADING))
U = X * s + Y * c              # вдоль судна (к носу), курс 30° по часовой: нос = (sin, cos)
V = X * c - Y * s              # поперёк (к правому борту)
# расстояние до контура корпуса в плане (эллипс со сплющенными концами)
E = np.sqrt((U / HALF_L) ** 2 + (V / HALF_B) ** 2)
D = np.maximum(E - 1.0, 0.0) * HALF_B                       # примерно метры от борта
inside = E < 1.0
port = V < 0
# нанос ила у левого борта (подветренная сторона) и общий «вал» у корпуса
H += np.where(port, 0.70, 0.30) * np.exp(-D / np.where(port, 1.6, 0.8)) * (1 - 0.3 * np.abs(U) / HALF_L)
# размыв у носа и кормы (конец корпуса, течение огибает)
ends = np.clip((np.abs(U) - HALF_L * 0.6) / (HALF_L * 0.5), 0, 1)
H -= 0.35 * ends * np.exp(-((D - 0.9) / 0.7) ** 2)
# под корпусом дно поднято до линии ила (скрыть срез скана)
H = np.where(inside, np.maximum(H, 0.25), H)
# маска песка: пятна вдали, у корпуса ил
sand = np.clip(0.1 + 2.2 * value_noise(X, Y, 7.0, 4), 0, 1) * np.clip((D - 2.5) / 3.0, 0, 1)
# крупные пятна тона: органический ил темнее (0,7), промытые участки светлее (1,1); у корпуса темнее
TONE = np.clip(0.9 + 0.22 * value_noise(X, Y, 5.0, 6) + 0.08 * value_noise(X, Y, 1.7, 7), 0.65, 1.15)
TONE = np.where(D < 1.5, TONE * 0.85, TONE)
# рябь на песке (волны 0,6 м, 2 см)
H += 0.02 * sand * np.sin(2 * np.pi * (X * 0.8 + Y * 0.6) / 0.6 + 2 * value_noise(X, Y, 4.0, 5))

bm = bmesh.new()
verts = [[bm.verts.new((X[j, i], Y[j, i], H[j, i])) for i in range(n)] for j in range(n)]
uv_l = bm.loops.layers.uv.new("UVMap")
col_l = bm.loops.layers.color.new("Col")       # RGB: тон крупных пятен, A: доля песка (один слой для glTF)
for j in range(n - 1):
    for i in range(n - 1):
        f = bm.faces.new([verts[j][i], verts[j][i + 1], verts[j + 1][i + 1], verts[j + 1][i]])
        for lp in f.loops:
            co = lp.vert.co
            lp[uv_l].uv = (co.x / 3.0, co.y / 3.0)          # текстура 3 × 3 м
            jj = int(round((co.y + SIZE / 2) / RES))
            ii = int(round((co.x + SIZE / 2) / RES))
            sv = float(sand[jj, ii])
            tb = float(TONE[jj, ii])
            lp[col_l] = (tb / 1.15, tb * 0.98 / 1.15, tb * 0.95 / 1.15, sv)   # тон /1,15: цвет в [0, 1]
me = bpy.data.meshes.new("Seabed")
bm.to_mesh(me)
bm.free()
for p in me.polygons:
    p.use_smooth = True
seabed = bpy.data.objects.new("Seabed", me)
coll.objects.link(seabed)
seabed.data.materials.append(M_SEABED)


def ground(x, y):
    """Высота дна в точке (билинейно по сетке)."""
    fi = (x + SIZE / 2) / RES
    fj = (y + SIZE / 2) / RES
    i0, j0 = int(fi), int(fj)
    tx, ty = fi - i0, fj - j0
    return float(H[j0, i0] * (1 - tx) * (1 - ty) + H[j0, i0 + 1] * tx * (1 - ty)
                 + H[j0 + 1, i0] * (1 - tx) * ty + H[j0 + 1, i0 + 1] * tx * ty)


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
hawse = world_of_ship((0.35, HALF_L - 0.6, 1.7))
# путь цепи: от клюза провисом к дну у носа, затем по дну с изгибом к скобе якоря
touch = Vector((hawse.x, hawse.y, 0)) + fwd * 0.9
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
# камни: несколько крупных на склонах, мелкие группами
rr = random.Random(7)
rocks = []
for g in range(6):                       # группы камней на склонах
    a = rr.uniform(0, 2 * math.pi)
    d = rr.uniform(9.0, 17.0)
    gx, gy = d * math.cos(a), d * math.sin(a)
    for k in range(rr.randint(1, 4)):
        x, y = gx + rr.uniform(-1.2, 1.2), gy + rr.uniform(-1.2, 1.2)
        sz = rr.uniform(0.12, 0.7) if k else rr.uniform(0.5, 1.1)
        rocks.append(rock("Rock_%d_%d" % (g, k), (sz, sz * rr.uniform(0.7, 1.2), sz * 0.55),
                          (x, y, ground(x, y) + sz * 0.1), g * 10 + k))

# ---------------- точки осмотра (по деталям скана, координаты судна: нос +Y, правый борт +X) ----------------
def ip(name, p_ship=None, p_world=None):
    e = bpy.data.objects.new(name, None)
    coll.objects.link(e)
    e.location = world_of_ship(p_ship) if p_ship is not None else p_world
    return e


IPS = [
    ip("IP_1_нос и форштевень", (0.0, 4.6, 1.3)),
    ip("IP_2_рубка окна и дверь", (-1.95, 0.3, 2.2)),          # снаружи левой стенки рубки и лееров (x ≈ −1,8 м)
    ip("IP_3_стрела на крыше рубки", (0.0, 0.5, 3.85)),
    ip("IP_4_корма", (0.0, -4.8, 1.4)),
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
            for n in [n for n in m.node_tree.nodes if n.type == "TEX_IMAGE"]:
                m.node_tree.nodes.remove(n)
    small = bpy.data.images.load(ROOT + "/godot/assets/wreck/malpas_basecolor.jpg", check_existing=False)
    small.name = "malpas_basecolor_4k"
    for m in hull.data.materials:                  # в .blend скана упакован исходник 8192²: подставить 4096²
        for n in m.node_tree.nodes:
            if n.type == "TEX_IMAGE":
                n.image = small
    os.makedirs(os.path.dirname(GLB), exist_ok=True)
    for o in bpy.context.view_layer.objects:
        o.select_set(o.users_collection[0] == coll and o.type in ("MESH", "EMPTY"))
    bpy.ops.export_scene.gltf(filepath=GLB, export_format="GLB", use_selection=True, export_apply=True,
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
    views = [((11, -9, 5.5), (0, 0, 1.0)), ((-10, 8, 4.0), (0, 0, 1.0)), ((0, 0, 24), (0, 0.01, 0)),
             (tuple(bow_tip + fwd * 6 + Vector((-c * 3, s * 3, 2.5))), tuple(anchor_xy * 0.5 + bow_tip * 0.5)),
             ((6, 3, 2.0), (0, 0, 1.2)), ((-4.5, -6, 1.6), (0, -2, 1.0)),
             (tuple(Vector(anc.location) + Vector((1.6, -1.2, 1.1))), tuple(anc.location)),          # якорь
             (tuple(world_of_ship((-4.5, 1.0, 1.2))), tuple(world_of_ship((-1.6, 0.0, 0.6)))),     # нанос у левого борта
             ((12.0, 9.0, 2.2), (7.0, 13.0, 0.0)),
             (tuple(Vector(props[0].location) + Vector((-1.6, -1.3, 0.9)) - side * 0.8), tuple(Vector(props[0].location) + side * 0.6))]                                              # дно вдали, песок
    for k, (loc, tgt) in enumerate(views):
        cam.location = loc
        cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = f"{render_dir}/site_{k}.png"
        bpy.ops.render.render(write_still=True)
        log("рендер", sc.render.filepath)

export_glb()   # после рендеров: узлы картинок MAT_* удаляются
