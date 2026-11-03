"""Игровой бассейн с 6 кольцами (этап 4, доработка): модель для Godot и «сухие» рендеры.

    blender -b --factory-startup --python blender/build_pool.py -- [--render <папка>]
Пишет godot/assets/pool/pool.glb и blender/pool_report.json.

Размеры и кольца по первой версии симулятора (Семенов Н. Н.): чаша 12 × 25 × 5 м, стенки 0,4 м,
иллюминаторы R 0,45 м на глубине 1,5 м (по одному на стене), полосы глубины через 1 м, кольца:
труба Ø0,06 м, радиус оси = просвет/2 + 0,03, две ножки Ø0,045 до дна, опоры 0,35 × 0,06 × 0,35 м, номер над кольцом.
Добавлено для достоверности (типовой спортивный бассейн, оценка): облицовка плиткой 125 мм, разметка
дорожек тёмно-синей плиткой (6 дорожек по 2 м, линии 0,25 м с «Т» на концах и мишенями на торцах),
переливной лоток с решёткой, обходная дорожка, 4 лестницы, 10 подводных светильников (по 5 на длинных
стенах на глубине 0,8 м).

Оси Blender: X восток, Y север (вдоль бассейна), Z вверх; поверхность воды Z = 0, дно Z = −5.
Экспорт glTF -> Godot: (x, z, −y), то есть север = −Z Godot, как NedGodot.
Имена для Godot: Ring_<n>_* (касания колец), PoolLight_<k> (подводные светильники), MAT_* (наборы текстур).
"""
import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

ROOT = "D:/Документы/ROV-Sim"
GLB = ROOT + "/godot/assets/pool/pool.glb"
REPORT = ROOT + "/blender/pool_report.json"
TEX = ROOT + "/godot/assets/textures"
W, L, D = 12.0, 25.0, 5.0
# север, восток, глубина, курс оси (° по часовой сверху), просвет — RingCourse.LAYOUT (game/ring_course.gd)
RINGS = [(-8.0, 0.0, 1.2, 0.0, 1.2), (-4.0, 1.8, 2.0, 20.0, 1.1), (0.0, 0.5, 3.2, -15.0, 1.0),
         (4.0, -2.2, 2.4, -25.0, 0.9), (7.5, -0.5, 3.6, 15.0, 0.8), (10.5, 1.5, 1.6, 25.0, 0.7)]
LIGHT_DEPTH = 0.8
LIGHTS_Y = [-10.0, -5.0, 0.0, 5.0, 10.0]

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
render_dir = argv[argv.index("--render") + 1] if "--render" in argv else None

bpy.ops.wm.read_factory_settings(use_empty=True)
coll = bpy.context.scene.collection


def log(*a):
    print("POOL", *a, flush=True)


# ---------------- материалы ----------------
def tex_mat(name, set_name, tint=(1, 1, 1)):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    d = f"{TEX}/{set_name}/{set_name}"
    img = nt.nodes.new("ShaderNodeTexImage")
    img.image = bpy.data.images.load(f"{d}_diff_1k.jpg", check_existing=True)
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs[0].default_value = 1.0
    mix.inputs[7].default_value = (*tint, 1)
    nt.links.new(img.outputs["Color"], mix.inputs[6])
    nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
    nimg = nt.nodes.new("ShaderNodeTexImage")
    nimg.image = bpy.data.images.load(f"{d}_nor_gl_1k.jpg", check_existing=True)
    nimg.image.colorspace_settings.name = "Non-Color"
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(nimg.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    bsdf.inputs["Roughness"].default_value = 0.25 if "pool" in set_name else 0.8
    return m


def plain(name, col, rough=0.5, metal=0.0, emit=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*col, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if emit:
        b.inputs["Emission Color"].default_value = (*col, 1)
        b.inputs["Emission Strength"].default_value = emit
    return m


M_TILE = tex_mat("MAT_pool_tiles", "pool_tiles")
M_LANE = tex_mat("MAT_pool_tiles__lane", "pool_tiles", (0.10, 0.17, 0.45))      # тёмно-синяя плитка
M_DECK = tex_mat("MAT_anti_skid_tiles", "anti_skid_tiles")
M_CONC = tex_mat("MAT_concrete_wall_006", "concrete_wall_006")
M_STEEL = plain("PLAIN_stainless", (0.55, 0.56, 0.58), 0.3, 1.0)
M_GRATE = plain("PLAIN_grate_white", (0.75, 0.76, 0.74), 0.5)
M_PIPE = plain("PLAIN_ring_orange", (0.62, 0.13, 0.02), 0.4)
M_SIGN = plain("PLAIN_sign_white", (0.80, 0.80, 0.76), 0.6)
M_TEXT = plain("PLAIN_sign_black", (0.02, 0.02, 0.025), 0.6)
M_GLASS = plain("PLAIN_porthole_glass", (0.02, 0.03, 0.035), 0.05, 0.0, 0.0)
M_GALLERY = plain("PLAIN_gallery", (0.35, 0.40, 0.45), 0.5, 0.0, 0.02)          # слабый свет из смотровой
M_LENS = plain("PLAIN_light_lens", (1.0, 0.95, 0.85), 0.1, 0.0, 22.0)           # ≈11000 кд/м² (2500 лм, Ø0,3 м)


# ---------------- геометрия ----------------
def mesh_obj(name, bm, mat):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    coll.objects.link(o)
    o.data.materials.append(mat)
    return o


def quad(name, corners, mat, uv_m=1.0):
    """Прямоугольник по 4 углам (против часовой, если смотреть с лицевой стороны); UV в метрах / uv_m."""
    bm = bmesh.new()
    vs = [bm.verts.new(c) for c in corners]
    f = bm.faces.new(vs)
    uv = bm.loops.layers.uv.new("UVMap")
    a, b, c = Vector(corners[0]), Vector(corners[1]), Vector(corners[3])
    eu, ev = (b - a).normalized(), (c - a).normalized()
    for lp in f.loops:
        p = lp.vert.co - a
        lp[uv].uv = (p.dot(eu) / uv_m, p.dot(ev) / uv_m)
    return mesh_obj(name, bm, mat)


def box(name, size, loc, mat, rot=(0, 0, 0), uv_m=1.0):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    uv = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:              # UV в метрах по наибольшим осям грани
        n = f.normal
        ax = sorted(range(3), key=lambda i: -abs(n[i]))[1:]
        for lp in f.loops:
            lp[uv].uv = (lp.vert.co[ax[0]] / uv_m, lp.vert.co[ax[1]] / uv_m)
    o = mesh_obj(name, bm, mat)
    o.location = loc
    o.rotation_euler = Euler([math.radians(x) for x in rot])
    return o


def cyl(name, r, h, loc, mat, rot=(0, 0, 0), seg=16):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r, radius2=r, depth=h, calc_uvs=True)
    o = mesh_obj(name, bm, mat)
    o.location = loc
    o.rotation_euler = Euler([math.radians(x) for x in rot])
    for p in o.data.polygons:
        p.use_smooth = True
    return o


def torus(name, R, r, loc, mat, rot, seg=(48, 10)):
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r, major_segments=seg[0],
                                     minor_segments=seg[1], location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    o.data.materials.append(mat)
    for p in o.data.polygons:
        p.use_smooth = True
    return o


def text(name, s, size, loc, rot, mat):
    bpy.ops.object.text_add(location=loc, rotation=rot)
    t = bpy.context.active_object
    t.data.body = s
    t.data.size = size
    t.data.extrude = 0.004
    t.data.align_x = "CENTER"
    t.data.align_y = "CENTER"
    bpy.ops.object.convert(target="MESH")
    t = bpy.context.active_object
    t.name = name
    t.data.materials.clear()
    t.data.materials.append(mat)
    return t


hw, hl = W / 2, L / 2
TOP = 0.15            # верх стенки (кромка лотка) над водой
# чаша: дно и 4 стены, лицом внутрь
quad("Floor", [(-hw, -hl, -D), (hw, -hl, -D), (hw, hl, -D), (-hw, hl, -D)], M_TILE)
quad("Wall_S", [(-hw, -hl, -D), (-hw, -hl, TOP), (hw, -hl, TOP), (hw, -hl, -D)][::-1][::-1], M_TILE)
walls = {
    "Wall_S": [(hw, -hl, -D), (-hw, -hl, -D), (-hw, -hl, TOP), (hw, -hl, TOP)],
    "Wall_N": [(-hw, hl, -D), (hw, hl, -D), (hw, hl, TOP), (-hw, hl, TOP)],
    "Wall_W": [(-hw, -hl, -D), (-hw, hl, -D), (-hw, hl, TOP), (-hw, -hl, TOP)],
    "Wall_E": [(hw, hl, -D), (hw, -hl, -D), (hw, -hl, TOP), (hw, hl, TOP)],
}
bpy.data.objects.remove(bpy.data.objects["Wall_S"], do_unlink=True)
for nm, cs in walls.items():
    # лицом внутрь: порядок углов подобран так, чтобы нормаль смотрела в бассейн
    o = quad(nm, cs[::-1] if nm in ("Wall_S", "Wall_E") else cs, M_TILE)
for o in [ob for ob in coll.objects if ob.name.startswith("Wall_") or ob.name == "Floor"]:
    me = o.data
    c = sum((v.co for v in me.vertices), Vector()) / len(me.vertices)
    n = me.polygons[0].normal
    if n.dot(-c.normalized() if o.name != "Floor" else Vector((0, 0, 1))) < 0:
        me.flip_normals()
# переливной лоток и решётка по периметру, обходная дорожка
for nm, size, loc in [("Gutter_S", (W + 0.6, 0.3, 0.12), (0, -hl - 0.15, TOP - 0.06)),
                      ("Gutter_N", (W + 0.6, 0.3, 0.12), (0, hl + 0.15, TOP - 0.06)),
                      ("Gutter_W", (0.3, L, 0.12), (-hw - 0.15, 0, TOP - 0.06)),
                      ("Gutter_E", (0.3, L, 0.12), (hw + 0.15, 0, TOP - 0.06))]:
    box(nm, size, loc, M_GRATE, uv_m=0.05)
box("Deck", (W + 8, L + 8, 0.3), (0, 0, TOP - 0.15 - 0.06), M_DECK)
bpy.ops.object.select_all(action="DESELECT")
# вырез под воду в настиле: вместо булевой операции — 4 полосы настила вокруг
bpy.data.objects.remove(bpy.data.objects["Deck"], do_unlink=True)
for nm, size, loc in [("Deck_S", (W + 8, 3.7, 0.3), (0, -hl - 0.3 - 1.85, TOP - 0.15)),
                      ("Deck_N", (W + 8, 3.7, 0.3), (0, hl + 0.3 + 1.85, TOP - 0.15)),
                      ("Deck_W", (3.7, L + 0.6, 0.3), (-hw - 0.3 - 1.85, 0, TOP - 0.15)),
                      ("Deck_E", (3.7, L + 0.6, 0.3), (hw + 0.3 + 1.85, 0, TOP - 0.15))]:
    box(nm, size, loc, M_DECK)

# разметка дорожек: 6 дорожек по 2 м, линии по центру дорожек, «Т» за 2 м до торцов, мишени на торцах
eps = 0.004
lane_x = [-5.0, -3.0, -1.0, 1.0, 3.0, 5.0]
for k, x in enumerate(lane_x):
    quad(f"Lane_{k}", [(x - 0.125, -hl + 2.0, -D + eps), (x + 0.125, -hl + 2.0, -D + eps),
                       (x + 0.125, hl - 2.0, -D + eps), (x - 0.125, hl - 2.0, -D + eps)], M_LANE)
    for sgn in (-1, 1):
        y = sgn * (hl - 2.0)
        quad(f"LaneT_{k}_{sgn}", [(x - 0.5, y - 0.125, -D + eps), (x + 0.5, y - 0.125, -D + eps),
                                  (x + 0.5, y + 0.125, -D + eps), (x - 0.5, y + 0.125, -D + eps)], M_LANE)
        yw = sgn * (hl - eps)
        cs = [(x - 0.125, yw, -D + 0.3), (x + 0.125, yw, -D + 0.3), (x + 0.125, yw, -0.3), (x - 0.125, yw, -0.3)]
        o = quad(f"Target_{k}_{sgn}", cs if sgn < 0 else cs[::-1], M_LANE)
        cs2 = [(x - 0.25, yw, -1.0), (x + 0.25, yw, -1.0), (x + 0.25, yw, -0.75), (x - 0.25, yw, -0.75)]
        quad(f"TargetX_{k}_{sgn}", cs2 if sgn < 0 else cs2[::-1], M_LANE)
# полосы глубины через 1 м на стенах (как в сборке): ряд синих плиток 0,125 м
for d in range(1, int(D)):
    z = -d
    for nm, cs in [("S", [(hw, -hl + eps, z), (-hw, -hl + eps, z), (-hw, -hl + eps, z + 0.125), (hw, -hl + eps, z + 0.125)]),
                   ("N", [(-hw, hl - eps, z), (hw, hl - eps, z), (hw, hl - eps, z + 0.125), (-hw, hl - eps, z + 0.125)]),
                   ("W", [(-hw + eps, -hl, z), (-hw + eps, hl, z), (-hw + eps, hl, z + 0.125), (-hw + eps, -hl, z + 0.125)]),
                   ("E", [(hw - eps, hl, z), (hw - eps, -hl, z), (hw - eps, -hl, z + 0.125), (hw - eps, hl, z + 0.125)])]:
        quad(f"DepthStripe_{nm}_{d}", cs, M_LANE)
# иллюминаторы: рама из нержавейки, тёмное стекло, за ним слабо освещённая смотровая
for nm, pos, rot in [("S", (0, -hl, -1.5), (90, 0, 0)), ("N", (0, hl, -1.5), (90, 0, 180)),
                     ("W", (-hw, 0, -1.5), (90, 0, -90)), ("E", (hw, 0, -1.5), (90, 0, 90))]:
    torus(f"PortholeFrame_{nm}", 0.47, 0.035, pos, M_STEEL, [math.radians(a) for a in rot], (40, 8))
    c = cyl(f"PortholeGlass_{nm}", 0.45, 0.01, pos, M_GLASS, rot, seg=40)
# подводные светильники на длинных стенах
lights = []
for side, x, rz in [("W", -hw, -90), ("E", hw, 90)]:
    for k, y in enumerate(LIGHTS_Y):
        nm = f"PoolLight_{side}{k}"
        pos = (x + (0.03 if side == "W" else -0.03), y, -LIGHT_DEPTH)
        torus(nm + "_ring", 0.16, 0.025, pos, M_STEEL, [math.radians(90), 0, math.radians(rz)], (32, 8))
        lens = cyl(nm, 0.15, 0.03, pos, M_LENS, (90, 0, rz), seg=24)
        lights.append({"name": nm, "pos": [round(v, 3) for v in pos], "dir": [1 if side == "W" else -1, 0, 0]})
# лестницы: две стойки с загибом через борт и 3 ступени
for k, (x, y, inward) in enumerate([(-hw, -9.0, 1), (hw, -9.0, -1), (-hw, 9.0, 1), (hw, 9.0, -1)]):
    for dy in (-0.25, 0.25):
        cyl(f"LadderRail_{k}_{dy}", 0.022, 1.6, (x + inward * 0.12, y + dy, -0.55), M_STEEL)
        torus(f"LadderBend_{k}_{dy}", 0.12, 0.022, (x, y + dy, 0.25), M_STEEL,
              [math.radians(90), 0, 0], (24, 8))
    for s in range(3):
        box(f"LadderStep_{k}_{s}", (0.08, 0.5, 0.03), (x + inward * 0.12, y, -0.3 - s * 0.3), M_STEEL)

# кольца
for i, (n_, e_, d_, psi, clear) in enumerate(RINGS):
    num = i + 1
    c = Vector((e_, n_, -d_))
    p = math.radians(psi)
    rot = Matrix.Rotation(-p, 4, "Z") @ Matrix.Rotation(math.radians(90), 4, "X")
    R = clear / 2 + 0.03
    t = torus(f"Ring_{num}_pipe", R, 0.03, c, M_PIPE, rot.to_euler(), (64, 12))
    lat = Vector((math.cos(p), -math.sin(p), 0))
    for sgn in (-1, 1):
        top = c + lat * sgn * R
        h = D + top.z
        cyl(f"Ring_{num}_leg_{sgn}", 0.0225, h, (top.x, top.y, top.z - h / 2), M_STEEL, seg=12)
        box(f"Ring_{num}_base_{sgn}", (0.35, 0.35, 0.06), (top.x, top.y, -D + 0.03), M_CONC, uv_m=0.5)
    sp = c + Vector((0, 0, R + 0.33))
    cyl(f"Ring_{num}_post", 0.012, 0.3, c + Vector((0, 0, R + 0.17)), M_STEEL, seg=8)
    box(f"Ring_{num}_sign", (0.28, 0.02, 0.28), sp, M_SIGN, (0, 0, -psi))
    for face, off in ((0, -0.012), (180, 0.012)):
        fv = Vector((math.sin(p), math.cos(p), 0)) * off
        text(f"Ring_{num}_num_{face}", str(num), 0.2, sp + fv,
             (math.radians(90), 0, math.radians(-psi + face)), M_TEXT)

# ---------------- отчёт ----------------
bpy.context.view_layer.update()
meshes = [o for o in coll.objects if o.type == "MESH"]
tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in meshes)
rep = {"tris_total": tris, "objects": len(meshes), "lights": lights, "light_depth": LIGHT_DEPTH}
json.dump(rep, open(REPORT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
log("треугольников", tris, "объектов", len(meshes))
bpy.ops.wm.save_as_mainfile(filepath=ROOT + "/blender/pool.blend")

# ---------------- сухие рендеры (без воды): свет как в зале + подводные светильники ----------------
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
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.7, 0.72, 0.75, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.8
    sc.world = world
    for k, y in enumerate([-8, 0, 8]):
        ld = bpy.data.lights.new(f"hall{k}", "AREA")
        ld.energy = 3000
        ld.size = 6
        lo = bpy.data.objects.new(f"hall{k}", ld)
        lo.location = (0, y, 8)
        coll.objects.link(lo)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.lens = 22
    coll.objects.link(cam)
    sc.camera = cam
    views = [((5.5, -12.0, 1.5), (0, 0, -3.0)), ((-5.0, 11.5, -0.5), (1.0, -3.0, -3.0)),
             ((0.0, -10.5, -1.2), (0.0, -8.0, -1.2)), ((3.0, -1.0, -3.0), (0.5, 0.0, -3.2)),
             ((-5.2, -9.5, -0.6), (-6.0, -9.0, -0.3)), ((0, 0, 18), (0, 0.01, -5))]
    for k, (loc, tgt) in enumerate(views):
        cam.location = loc
        cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = f"{render_dir}/pool_{k}.png"
        bpy.ops.render.render(write_still=True)
        log("рендер", sc.render.filepath)


def export_glb():
    for m in bpy.data.materials:              # картинки наборов Godot берёт сам по имени MAT_*
        if m.name.startswith("MAT_") and m.use_nodes:
            for n in [n for n in m.node_tree.nodes if n.type == "TEX_IMAGE"]:
                m.node_tree.nodes.remove(n)
    os.makedirs(os.path.dirname(GLB), exist_ok=True)
    for o in bpy.context.view_layer.objects:
        o.select_set(o.type == "MESH" and not o.name.startswith(("hall", "cam")))
    bpy.ops.export_scene.gltf(filepath=GLB, export_format="GLB", export_copyright="ROV-Sim, Kholopov E. G. (Холопов Е. Г.), 2026, CC BY 4.0",  # то же пишет work/tools/stamp_glb.py
        use_selection=True, export_apply=True,
                              export_yup=True)
    log("glb", os.path.getsize(GLB) // 1024, "КБ")


export_glb()
