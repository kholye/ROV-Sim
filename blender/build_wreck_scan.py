"""Судно для сцены «корабль» из скана «Malpas Metal Boat Wreck» (artfletch, CC BY 4.0, Sketchfab;
лежит в data/models/malpas_metal_boat_wreck, в репозиторий не входит).

Запуск без окна:
    blender -b --factory-startup --python blender/build_wreck_scan.py -- [--render <папка>]

Что делает:
 1. импорт glTF скана, объединение частей;
 2. срез грунтовой подложки скана: грани ниже уровня ила (Z_CUT) и обращённые вверх грани грунта
    до Z_MUD_UP; оторванные кусочки меньше MIN_ISLAND граней удаляются. Корпус ниже ила в сцене
    всё равно скрыт дном и наносами;
 3. упрощение (Decimate, collapse) до TARGET_TRIS треугольников;
 4. текстура 8192² уменьшается до TEX_SIZE, пишется в godot/assets/wreck/;
 5. начало координат: середина судна на уровне ила; нос вдоль +Y Blender (−Z Godot);
 6. отчёт blender/wreck_scan_report.json; сохранение blender/wreck_scan.blend;
 7. с --render: «сухие» рендеры (Cycles, студийный свет, без воды) в указанную папку.
"""
import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

ROOT = "D:/Документы/ROV-Sim"
SRC = ROOT + "/data/models/malpas_metal_boat_wreck/scene.gltf"
TEX_OUT = ROOT + "/godot/assets/wreck/malpas_basecolor.jpg"
BLEND = ROOT + "/blender/wreck_scan.blend"
REPORT = ROOT + "/blender/wreck_scan_report.json"

Z_CUT = 1.12        # ниже этого всё (подложка, ил, днище) срезается, м скана
Z_MUD_UP = 1.32     # грани, смотрящие вверх (нормаль z > 0,7), ниже этого: поверхность грунта
MIN_ISLAND = 150    # оторванные кусочки грунта меньше этого (граней) удаляются
TARGET_TRIS = 80000
TEX_SIZE = 4096

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
render_dir = argv[argv.index("--render") + 1] if "--render" in argv else None


def log(*a):
    print("WRECKSCAN", *a, flush=True)


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=SRC)
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
for o in meshes:
    o.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
bpy.ops.object.join()
ship = bpy.context.view_layer.objects.active
ship.name = "WreckHull"
# применить трансформации импорта (glTF Y-up -> Z-up), чтобы работать в мировых координатах
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
for o in list(bpy.context.scene.objects):
    if o.type != "MESH":
        bpy.data.objects.remove(o, do_unlink=True)
tris0 = sum(len(p.vertices) - 2 for p in ship.data.polygons)
log("исходно треугольников", tris0)

# ---- 2. срез грунта ----
bm = bmesh.new()
bm.from_mesh(ship.data)
# glTF разрывает сетку по швам развёртки: сшить совпадающие вершины (UV хранятся в углах граней и не теряются),
# иначе «оторванными кусками» окажутся куски корпуса
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
bm.faces.ensure_lookup_table()
kill = [f for f in bm.faces if f.calc_center_median().z < Z_CUT
        or (f.normal.z > 0.7 and f.calc_center_median().z < Z_MUD_UP)]
bmesh.ops.delete(bm, geom=kill, context="FACES")
# оторванные кусочки
bm.faces.ensure_lookup_table()
seen = set()
islands = []
for f in bm.faces:
    if f.index in seen:
        continue
    stack, isl = [f], []
    seen.add(f.index)
    while stack:
        g = stack.pop()
        isl.append(g)
        for e in g.edges:
            for h in e.link_faces:
                if h.index not in seen:
                    seen.add(h.index)
                    stack.append(h)
    islands.append(isl)
small = [f for isl in islands if len(isl) < MIN_ISLAND for f in isl]
bmesh.ops.delete(bm, geom=small, context="FACES")
bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
bm.to_mesh(ship.data)
bm.free()
log("после среза грунта", len(ship.data.polygons), "граней; островов", len(islands), "удалено мелких", len(small))

# ---- 3. упрощение ----
tris1 = sum(len(p.vertices) - 2 for p in ship.data.polygons)
mod = ship.modifiers.new("Decimate", "DECIMATE")
mod.decimate_type = "COLLAPSE"
mod.ratio = min(1.0, TARGET_TRIS / tris1)
mod.use_collapse_triangulate = True
bpy.ops.object.modifier_apply(modifier=mod.name)
tris2 = sum(len(p.vertices) - 2 for p in ship.data.polygons)
log("после упрощения", tris2)

# ---- 5. оси и начало координат ----
pts = [ship.matrix_world @ v.co for v in ship.data.vertices]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
size = hi - lo
# длинная ось скана по X; нос там, где корпус уже (меньше вершин у края по Y-ширине): определяем
# по ширине корпуса у краёв на высоте 1,5-2,0 м
def width_at(xa, xb):
    ys = [p.y for p in pts if xa <= p.x <= xb and 1.4 <= p.z <= 2.2]
    return (max(ys) - min(ys)) if ys else 0.0
w_minus = width_at(lo.x, lo.x + 1.0)
w_plus = width_at(hi.x - 1.0, hi.x)
bow_plus_x = w_plus < w_minus
log("габарит", tuple(round(v, 2) for v in size), "ширина у краёв −X/+X", round(w_minus, 2), round(w_plus, 2),
    "нос в", "+X" if bow_plus_x else "−X")
# середина по ширине — по самому корпусу на высоте 1,4-2,6 м (леера и швартовы расширяют рамку несимметрично)
hull_band = [p for p in pts if 1.4 <= p.z <= 2.6]
if bow_plus_x:
    cy = (min(p.y for p in hull_band) + max(p.y for p in hull_band)) / 2
else:
    cy = (min(p.y for p in hull_band) + max(p.y for p in hull_band)) / 2
center = Vector(((lo.x + hi.x) / 2, cy, Z_CUT))
log("середина корпуса по ширине", round(cy, 3), "середина рамки", round((lo.y + hi.y) / 2, 3))
rot = Matrix.Rotation(math.radians(90 if bow_plus_x else -90), 4, "Z")   # нос -> +Y
ship.data.transform(rot @ Matrix.Translation(-center))
ship.data.update()

# ---- 4. текстура ----
img = next(i for i in bpy.data.images if i.size[0] > 0)
if img.size[0] > TEX_SIZE:
    img.scale(TEX_SIZE, TEX_SIZE)
os.makedirs(os.path.dirname(TEX_OUT), exist_ok=True)
img.filepath_raw = TEX_OUT
img.file_format = "JPEG"
bpy.context.scene.render.image_settings.quality = 90
img.save()
log("текстура", img.size[:], TEX_OUT)

pts = [v.co for v in ship.data.vertices]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
rep = {"source": "Malpas Metal Boat Wreck, artfletch, CC BY 4.0, https://sketchfab.com/3d-models/malpas-metal-boat-wreck-7a2c49c1be2c48a3a4d80a3f27dae205",
       "tris_source": tris0, "tris_after_cut": tris1, "tris_final": tris2,
       "bbox_min": [round(v, 3) for v in lo], "bbox_max": [round(v, 3) for v in hi],
       "size_m": [round(v, 3) for v in hi - lo], "z_cut_scan": Z_CUT, "texture": TEX_SIZE}
json.dump(rep, open(REPORT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
log("отчёт", json.dumps(rep, ensure_ascii=False))
bpy.ops.wm.save_as_mainfile(filepath=BLEND)

# ---- 7. сухие рендеры ----
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
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.55, 0.57, 0.6, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.6
    sc.world = world
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 3.0
    sun.rotation_euler = (math.radians(50), 0, math.radians(35))
    sc.collection.objects.link(sun)
    # серая плоскость-пол (без воды и ила), чтобы было видно, где срез
    bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 0, 0))
    floor = bpy.context.active_object
    m = bpy.data.materials.new("floor")
    m.use_nodes = True
    next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED").inputs["Base Color"].default_value = (0.25, 0.25, 0.25, 1)
    floor.data.materials.append(m)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.lens = 35
    sc.collection.objects.link(cam)
    sc.camera = cam
    c = Vector((0, 0, hi.z * 0.4))
    r = max(hi.x - lo.x, hi.y - lo.y) * 0.95
    for k, (az, el) in enumerate([(35, 0.3), (145, 0.25), (230, 0.3), (320, 0.4), (90, 0.08), (0, 1.3)]):
        a = math.radians(az)
        cam.location = c + Vector((r * math.cos(a), r * math.sin(a), r * el))
        cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = f"{render_dir}/dry_{k}.png"
        bpy.ops.render.render(write_still=True)
        log("рендер", sc.render.filepath)
