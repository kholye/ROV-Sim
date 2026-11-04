"""Лабораторный бассейн кафедры 3 × 3 × 3 м (тестовая сцена): модель для Godot и «сухие» рендеры.

    blender -b --factory-startup --python blender/build_lab_pool.py -- [--render <папка>]
Пишет godot/assets/lab/lab_pool.glb.

По словам автора (2026-11-02): стены — бетон с налётом и илом, дно — чёрная резина, тоже в иле.
Ил: смесь второго набора текстур по альфе цвета вершин (MAT_<основа>__brown_mud_03): на дне пятнами, на стенах —
только узкой полосой у дна (по фото автора 2026-11-04 стены — гладкий светлый бетон с потёками и вертикальными
швами, не грязь). Иллюминатор: круглое отверстие в западной стене с толстым откосом в грязи и ржавчине и тёмным
стеклом (по фото; диаметр 0,45 м, центр на глубине 1,2 м посередине стены — оценка). Планшет мишени (10 секторов, альбедо по эталону Холопова из
light_params.json, белая рамка, чёрный фон) висит на северной стене. Лестницы нет (по данным автора).
Сверху бассейн закрыт крышкой из 6 секций, открыта одна — через неё опускали аппарат (по данным автора);
раскладка 3 × 2 секции по 1,0 × 1,5 м и открытая — средняя южная (над стартом аппарата) — оценка.
Оси: X восток, Y север, Z вверх; вода Z = 0, дно Z = −3; центр бассейна в начале координат.
"""
import json
import math
import os
import random
import sys

import bmesh
import bpy
from mathutils import Vector

ROOT = "D:/Документы/ROV-Sim"
GLB = ROOT + "/godot/assets/lab/lab_pool.glb"
TEX = ROOT + "/godot/assets/textures"
PARAMS = ROOT + "/godot/physics/light_params.json"
S = 3.0
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
render_dir = argv[argv.index("--render") + 1] if "--render" in argv else None

bpy.ops.wm.read_factory_settings(use_empty=True)
coll = bpy.context.scene.collection
alb = json.load(open(PARAMS, encoding="utf-8"))["plate_albedo_rgb"]["value"]


def mix_mat(name, base, second):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    i1 = nt.nodes.new("ShaderNodeTexImage")
    i1.image = bpy.data.images.load(f"{TEX}/{base}/{base}_diff_1k.jpg", check_existing=True)
    i2 = nt.nodes.new("ShaderNodeTexImage")
    i2.image = bpy.data.images.load(f"{TEX}/{second}/{second}_diff_1k.jpg", check_existing=True)
    vc = nt.nodes.new("ShaderNodeVertexColor")
    vc.layer_name = "Col"
    mx = nt.nodes.new("ShaderNodeMix")
    mx.data_type = "RGBA"
    nt.links.new(vc.outputs["Alpha"], mx.inputs["Factor"])
    nt.links.new(i1.outputs["Color"], mx.inputs[6])
    nt.links.new(i2.outputs["Color"], mx.inputs[7])
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs[0].default_value = 1.0
    nt.links.new(mx.outputs[2], mul.inputs[6])
    nt.links.new(vc.outputs["Color"], mul.inputs[7])
    nt.links.new(mul.outputs[2], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.9
    return m


def plain(name, col, rough=0.9, metal=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*col, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    return m


M_WALL = mix_mat("MAT_concrete_wall_006__brown_mud_03", "concrete_wall_006", "brown_mud_03")
M_FLOOR = mix_mat("MAT_rubber_tiles__brown_mud_03", "rubber_tiles", "brown_mud_03")


def noise2(x, y, seed):
    r = random.Random(seed)
    h = 0.0
    for _ in range(5):
        a = r.uniform(0, 2 * math.pi)
        k = 2 * math.pi / r.uniform(0.5, 1.6)
        h += math.sin(k * (x * math.cos(a) + y * math.sin(a)) + r.uniform(0, 6.28))
    return h / 5


def grid(name, origin, eu, ev, nu, nv, mat, silt_fn, uv_m=1.0):
    """Сетка nu × nv на плоскости origin + u·eu + v·ev; цвет вершин: RGB тон, A ил (silt_fn(u, v))."""
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    col = bm.loops.layers.color.new("Col")
    lu, lv = eu.length, ev.length
    vs = [[bm.verts.new(origin + eu * (i / nu) + ev * (j / nv)) for i in range(nu + 1)] for j in range(nv + 1)]
    for j in range(nv):
        for i in range(nu):
            f = bm.faces.new([vs[j][i], vs[j][i + 1], vs[j + 1][i + 1], vs[j + 1][i]])
            for lp, (ii, jj) in zip(f.loops, [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]):
                u, v = ii / nu * lu, jj / nv * lv
                lp[uvl].uv = (u / uv_m, v / uv_m)
                a, tone = silt_fn(u, v)
                lp[col] = (tone, tone, tone, a)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    coll.objects.link(o)
    o.data.materials.append(mat)
    return o


h = S / 2
# дно: пятна ила, гуще у стен
def floor_silt(u, v):
    x, y = u - h, v - h
    edge = max(abs(x), abs(y)) / h
    a = min(max(0.05 + 0.75 * noise2(x, y, 3) + 0.5 * edge ** 3, 0.0), 1.0)
    return a, 0.9 + 0.1 * noise2(x, y, 9)


grid("Floor", Vector((-h, -h, -S)), Vector((S, 0, 0)), Vector((0, S, 0)), 24, 24, M_FLOOR, floor_silt, 0.5)


# стены: ил полосой у дна (до ~0,4 м) и подтёки, налёт выше
def wall_silt_f(seed):
    def f(u, v):
        z = v                                         # высота от дна
        band = math.exp(-z / 0.12)                    # ил только у самого дна
        a = min(max(0.9 * band + 0.05 * noise2(u, z, seed + 1), 0.0), 1.0)
        return a, 1.0 + 0.08 * noise2(u, z * 2, seed + 2)     # светлый бетон с лёгкими пятнами
    return f


for k, (o, eu) in enumerate([(Vector((h, -h, -S)), Vector((-S, 0, 0))), (Vector((-h, h, -S)), Vector((S, 0, 0))),
                             (Vector((-h, -h, -S)), Vector((0, S, 0))), (Vector((h, h, -S)), Vector((0, -S, 0)))]):
    grid(f"Wall_{k}", o, eu, Vector((0, 0, S + 0.15)), 24, 24, M_WALL, wall_silt_f(20 + k), 1.0)
# швы опалубки: тонкие тёмные вертикальные полосы (по фото), по две на стену (места — оценка)
M_SEAM = plain("PLAIN_wall_seam", (0.05, 0.045, 0.04), 0.9)
for k, (c, n, t) in enumerate([((0, -h, 0), (0, 1, 0), (1, 0, 0)), ((0, h, 0), (0, -1, 0), (1, 0, 0)),
                               ((-h, 0, 0), (1, 0, 0), (0, 1, 0)), ((h, 0, 0), (-1, 0, 0), (0, 1, 0))]):
    for off in (-0.62, 0.81):
        bpy.ops.mesh.primitive_cube_add(size=1)
        sm = bpy.context.active_object
        sm.name = f"Seam_{k}_{off}"
        sm.location = (c[0] + t[0] * off + n[0] * 0.001, c[1] + t[1] * off + n[1] * 0.001, -S / 2 + 0.07)
        sm.scale = (max(abs(t[0]) * 0.006, abs(n[0]) * 0.001), max(abs(t[1]) * 0.006, abs(n[1]) * 0.001), S + 0.14)
        sm.data.materials.append(M_SEAM)

# иллюминатор в западной стене (Wall_2): отверстие, откос глубиной 0,15 м, стекло в глубине
PORT_R, PORT_DEPTH, PORT_Z = 0.225, 0.15, -1.2
wall2 = bpy.data.objects["Wall_2"]
cut = bpy.data.objects.new("PortCut", bpy.data.meshes.new("PortCut"))
coll.objects.link(cut)
bm = bmesh.new()
bmesh.ops.create_cone(bm, cap_ends=True, segments=48, radius1=PORT_R, radius2=PORT_R, depth=0.4)
bm.to_mesh(cut.data)
bm.free()
cut.location = (-h, 0, PORT_Z)
cut.rotation_euler = (0, math.radians(90), 0)
mod = wall2.modifiers.new("port", "BOOLEAN")
mod.operation = "DIFFERENCE"
mod.object = cut
bpy.context.view_layer.objects.active = wall2
bpy.ops.object.modifier_apply(modifier="port")
bpy.data.objects.remove(cut)
M_REVEAL = bpy.data.materials.new("MAT_concrete_wall_006")   # откос — тот же бетон (по фото светлый)
M_SEDIM = bpy.data.materials.new("MAT_brown_mud_03")         # осадок и ржавые потёки на нижней части откоса


def tube(name, r, a0, a1, mat, inset=0.0):
    """Часть цилиндра откоса (ось — запад, от стены вглубь на PORT_DEPTH), нормали к оси отверстия."""
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    n = max(4, int(48 * (a1 - a0) / (2 * math.pi)))
    ring = []
    for i in range(n + 1):
        a = a0 + (a1 - a0) * i / n
        y, z = r * math.cos(a), PORT_Z + r * math.sin(a)
        ring.append((bm.verts.new((-h - inset, y, z)), bm.verts.new((-h - PORT_DEPTH + 0.01, y, z)), a))
    for i in range(n):
        v0, v1, aa = ring[i]
        w0, w1, ab = ring[i + 1]
        f = bm.faces.new([v0, v1, w1, w0])
        for lp, (a, d) in zip(f.loops, [(aa, 0), (aa, 1), (ab, 1), (ab, 0)]):
            lp[uvl].uv = (a * r / 0.5, d * PORT_DEPTH / 0.5)
    bm.normal_update()
    for f in bm.faces:                                # нормаль — к оси отверстия (внутрь трубы)
        c = f.calc_center_median()
        if f.normal.dot(Vector((c.x, 0, PORT_Z)) - c) < 0:
            f.normal_flip()
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    coll.objects.link(o)
    o.data.materials.append(mat)
    return o


tube("PortReveal", PORT_R, 0.0, 2 * math.pi, M_REVEAL)
tube("PortSediment", PORT_R - 0.004, math.radians(205), math.radians(330), M_SEDIM, 0.004)
bpy.ops.mesh.primitive_circle_add(vertices=48, radius=PORT_R, fill_type="NGON", location=(-h - PORT_DEPTH + 0.02, 0, PORT_Z),
                                  rotation=(0, math.radians(90), 0))
gl = bpy.context.active_object
gl.name = "PortGlass"
gl.data.materials.append(plain("PLAIN_port_glass", (0.015, 0.016, 0.014), 0.15))
# крышка: 6 секций 1,0 × 1,5 м (3 по востоку × 2 по северу) на борту бассейна, открыта средняя южная — она
# поднята на петлях у южного борта и стоит вертикально (раскладка и материал — оценка)
M_LID = plain("PLAIN_lid_plywood", (0.16, 0.14, 0.12), 0.85)
M_FRAME = plain("PLAIN_lid_frame", (0.10, 0.10, 0.10), 0.6, 1.0)
LID_Z = 0.15 + 0.01
for i in range(3):
    for j in range(2):
        x0, y0 = -h + i * 1.0, -h + j * 1.5
        bpy.ops.mesh.primitive_cube_add(size=1)
        lp = bpy.context.active_object
        lp.data.materials.append(M_LID)
        if i == 1 and j == 0:
            lp.name = "LidOpen"
            lp.scale = (0.98, 0.02, 1.48)
            lp.location = (x0 + 0.5, y0 - 0.02, LID_Z + 0.74)
        else:
            lp.name = f"Lid_{i}{j}"
            lp.scale = (0.98, 1.48, 0.02)
            lp.location = (x0 + 0.5, y0 + 0.75, LID_Z)
for k, (loc, sc) in enumerate([((0, -0.0, LID_Z - 0.03), (S, 0.06, 0.04)), ((-0.5, 0, LID_Z - 0.03), (0.06, S, 0.04)),
                               ((0.5, 0, LID_Z - 0.03), (0.06, S, 0.04))]):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    fr = bpy.context.active_object
    fr.scale = sc
    fr.name = f"LidBeam_{k}"
    fr.data.materials.append(M_FRAME)


# планшеты: 2 × 5 секторов 0,14 × 0,08 м, чёрный фон-подложка слева, белая рамка (как рис. 3 статьи)
def plate(name, loc, rot):
    root = bpy.data.objects.new(name, None)
    coll.objects.link(root)
    root.location = loc
    root.rotation_euler = rot
    def q(nm, w, hh, x, y, z, col):
        bpy.ops.mesh.primitive_plane_add(size=1, location=(x, y, z))
        p = bpy.context.active_object
        p.scale = (w, hh, 1)
        p.name = f"{name}_{nm}"
        p.data.materials.append(plain(f"PLAIN_{name}_{nm}", col))
        p.parent = root
    q("frame", 0.40, 0.50, 0, 0, 0.000, (0.85, 0.85, 0.85))
    q("back", 0.36, 0.46, 0, 0, 0.001, tuple(alb[8]))
    for k in range(10):
        q(f"S{k + 1}", 0.14, 0.08, (k % 2 - 0.5) * 0.16 + 0.02, (2 - k // 2) * 0.09, 0.002, tuple(alb[k]))
    return root


plate("PlateWall", (0, h - 0.003, -1.5), (math.radians(90), 0, 0))

bpy.ops.wm.save_as_mainfile(filepath=ROOT + "/blender/lab_pool.blend")
tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in coll.objects if o.type == "MESH")
print("LAB треугольников", tris, flush=True)

if render_dir:
    os.makedirs(render_dir, exist_ok=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 64
    sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = 1280, 720
    sc.view_settings.view_transform = "AgX"
    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.6
    sc.world = world
    ld = bpy.data.lights.new("top", "AREA")
    ld.energy = 600
    ld.size = 3
    lo = bpy.data.objects.new("top", ld)
    lo.location = (0, 0, 2.5)
    coll.objects.link(lo)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.lens = 18
    coll.objects.link(cam)
    sc.camera = cam
    for k, (loc, tgt) in enumerate([((1.3, -1.35, -0.3), (-0.4, 0.6, -2.4)), ((0, -1.2, -1.5), (0, 1.5, -1.5)),
                                    ((0.4, -0.3, -1.6), (0, 0, -3)), ((-1.3, 1.3, -2.6), (1.5, -1.5, -2.0))]):
        cam.location = loc
        cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = f"{render_dir}/lab_{k}.png"
        bpy.ops.render.render(write_still=True)

for m in bpy.data.materials:
    if m.name.startswith("MAT_") and m.use_nodes:
        for n in [n for n in m.node_tree.nodes if n.type in ("TEX_IMAGE", "VERTEX_COLOR")]:   # с узлом цвета вершин экспортёр теряет альфу (маску ила)
            m.node_tree.nodes.remove(n)
os.makedirs(os.path.dirname(GLB), exist_ok=True)
for o in bpy.context.view_layer.objects:
    o.select_set(o.type in ("MESH", "EMPTY") and o.name not in ("cam", "top"))
bpy.ops.export_scene.gltf(filepath=GLB, export_format="GLB", export_copyright="ROV-Sim, Kholopov E. G. (Холопов Е. Г.), 2026, CC BY 4.0",  # то же пишет work/tools/stamp_glb.py
        use_selection=True, export_apply=True,
                          export_yup=True, export_vertex_color="ACTIVE")
print("LAB glb", os.path.getsize(GLB) // 1024, "КБ", flush=True)
