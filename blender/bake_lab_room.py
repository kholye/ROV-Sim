"""Запекание света зала над лабораторным бассейном (Cycles CPU) и выгрузка для Godot.

    blender -b --python blender/bake_lab_room.py -- [размер=4096] [выборок=64]
Читает blender/lab_room.blend, пишет godot/assets/lab/lab_room.glb (одна сетка, одна текстура со светом)
и godot/assets/lab/lab_room_bake.json (масштаб яркости).
- Свет — как в render_lab_room.py: трубки (свечение + прямоугольные источники), дневной свет окон.
- Яркость в кд/м²: в игре нет света зала, поэтому текстура хранит яркость (Combined), а масштаб подобран так,
  чтобы средняя освещённость щитов пола была E_зала (light_params.json, lab_hall_e — оценка): по второму
  запеканию «только свет» (Diffuse: прямой + отражённый, без цвета). Текстура в sRGB, 1,0 = L_ref.
- Стекло (шкафы) не выгружается: через стекло видно содержимое, а запечь прозрачность нельзя.
- Длинные рёбра делятся до ≤ 0,35 м: в игре зал из-под воды показывается со смещением вершин по закону
  преломления (окно Снелла), и крупные грани иначе гнулись бы неверно.
"""
import json
import math
import os
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Vector

ROOT = "D:/Документы/ROV-Sim"
args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
RES = int(args[0]) if args else 4096
SAMPLES = int(args[1]) if len(args) > 1 else 64
E_HALL = json.load(open(ROOT + "/godot/physics/light_params.json", encoding="utf-8"))["lab_hall_e"]["value"]
GLB = ROOT + "/godot/assets/lab/lab_room.glb"
TEXDIR = ROOT + "/blender/room_tex"

bpy.ops.wm.open_mainfile(filepath=ROOT + "/blender/lab_room.blend")
sc = bpy.context.scene
coll = sc.collection

# --- свет (как в render_lab_room.py)
for o in [o for o in sc.objects if o.name.startswith("LampTube_") and o.name.endswith("a")]:
    ld = bpy.data.lights.new(o.name + "_L", "AREA")
    ld.shape = "RECTANGLE"
    ld.size, ld.size_y = 1.2, 0.12
    ld.energy = 45.0
    ld.color = (1.0, 0.97, 0.9)
    lo = bpy.data.objects.new(o.name + "_L", ld)
    coll.objects.link(lo)
    bb = [o.matrix_world @ Vector(c) for c in o.bound_box]
    cen = sum(bb, Vector()) / 8
    lo.location = (cen.x, cen.y, cen.z - 0.02)
    lo.rotation_euler = (0, 0, o.rotation_euler.z)
for o in [o for o in sc.objects if o.name.endswith("_sky") and o.type == "MESH"]:
    bb = [o.matrix_world @ Vector(c) for c in o.bound_box]
    cen = sum(bb, Vector()) / 8
    ld = bpy.data.lights.new(o.name + "_L", "AREA")
    ld.size, ld.size_y = 0.9, 1.3
    ld.energy = 60.0
    ld.color = (0.85, 0.92, 1.0)
    lo = bpy.data.objects.new(o.name + "_L", ld)
    coll.objects.link(lo)
    lo.location = cen
    lo.rotation_euler = (Vector((0.0, 0.0, 1.0)) - cen).to_track_quat("-Z", "Y").to_euler()

# --- одна сетка: всё, кроме стекла
meshes = [o for o in coll.objects if o.type == "MESH"]
bpy.ops.object.select_all(action="DESELECT")
for o in meshes:
    o.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
bpy.ops.object.make_single_user(object=True, obdata=True)
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
bpy.ops.object.join()
hall = bpy.context.active_object
hall.name = "LabRoom"
bm = bmesh.new()
bm.from_mesh(hall.data)
gi = [i for i, m in enumerate(hall.data.materials) if m and m.name == "DEV_glass"]
bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index in gi], context="FACES")
# невидимые наружные грани массива стен (бока внешнего прямоугольника, верх и низ массива)
xs_ = [v.co.x for v in bm.verts]
ys_ = [v.co.y for v in bm.verts]
X0, X1, Y0, Y1 = min(xs_), max(xs_), min(ys_), max(ys_)
dead = []
for f in bm.faces:
    c = f.calc_center_median()
    if min(abs(c.x - X0), abs(c.x - X1), abs(c.y - Y0), abs(c.y - Y1)) < 1e-3:
        dead.append(f)
    elif abs(f.normal.z) > 0.9 and (abs(c.z - 2.74) < 1e-3 or abs(c.z - 0.28) < 1e-3 or abs(c.z - 2.77) < 1e-3):
        dead.append(f)                               # верх/низ массива стен и верх потолка
bmesh.ops.delete(bm, geom=dead, context="FACES")
# длинные рёбра — делить (UV интерполируются)
for _ in range(5):
    long_e = [e for e in bm.edges if e.calc_length() > 0.35]
    if not long_e:
        break
    bmesh.ops.subdivide_edges(bm, edges=long_e, cuts=1, use_grid_fill=True)
bmesh.ops.triangulate(bm, faces=bm.faces[:])
bm.to_mesh(hall.data)
bm.free()
print("BAKE треугольников", len(hall.data.polygons), flush=True)

# --- UV для запекания
uv_src = hall.data.uv_layers.active.name
bake_uv = hall.data.uv_layers.new(name="bake")
hall.data.uv_layers.active = bake_uv
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.002, area_weight=1.0)
bpy.ops.uv.pack_islands(rotate=True, margin=0.001)
bpy.ops.object.mode_set(mode="OBJECT")
for m in hall.data.materials:                        # материалы читают свои UV по имени
    for n in m.node_tree.nodes:
        if n.type == "TEX_IMAGE":
            uvn = m.node_tree.nodes.new("ShaderNodeUVMap")
            uvn.uv_map = uv_src
            m.node_tree.links.new(uvn.outputs["UV"], n.inputs["Vector"])

sc.render.engine = "CYCLES"
sc.cycles.device = "CPU"
sc.world = bpy.data.worlds.new("w")
sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.0


def bake(name, res, samples, kind, passes):
    img = bpy.data.images.new(name, res, res, float_buffer=True)
    for m in hall.data.materials:
        nt = m.node_tree
        t = nt.nodes.get("_bake") or nt.nodes.new("ShaderNodeTexImage")
        t.name = "_bake"
        t.image = img
        nt.nodes.active = t
    sc.cycles.samples = samples
    bpy.ops.object.bake(type=kind, pass_filter=passes, margin=4, uv_layer="bake")
    a = np.empty(res * res * 4, np.float32)
    img.pixels.foreach_get(a)
    return img, a.reshape(res, res, 4)


# 1) освещённость (без цвета) — для масштаба
_, irr = bake("irr", 512, 16, "DIFFUSE", {"DIRECT", "INDIRECT"})
# точки щитов пола в развёртке «bake»
plates_uv = []
for p in hall.data.polygons:
    if hall.data.materials[p.material_index].name == "ROOM_floor_red" and p.normal.z > 0.9:
        for li in p.loop_indices:
            plates_uv.append(tuple(hall.data.uv_layers["bake"].data[li].uv))
pu = np.array(plates_uv)
e_rel = np.mean([irr[min(int(v * 511), 511), min(int(u * 511), 511), :3].mean() for u, v in pu])
k = float(np.mean(E_HALL)) / (math.pi * e_rel)       # Diffuse-свет Cycles = E/π в единицах сцены
print("BAKE e_rel", e_rel, "k", k, flush=True)

# 2) яркость (Combined)
img, L = bake("room", RES, SAMPLES, "COMBINED", {"EMIT", "DIRECT", "INDIRECT", "DIFFUSE", "GLOSSY", "TRANSMISSION"})
Lv = L[..., :3]
L_REF = 120.0 / k                                    # 1,0 текстуры = 120 кд/м² (белая стена при 300 лк ≈ 76; трубки и окна насыщаются)
enc = np.clip(Lv / L_REF, 0, 1) ** (1 / 2.2)
out = bpy.data.images.new("lab_room_light", RES, RES)
px = np.ones((RES, RES, 4), np.float32)
px[..., :3] = enc
out.pixels.foreach_set(px.ravel())
out.filepath_raw = f"{TEXDIR}/lab_room_light.png"
out.file_format = "PNG"
out.save()
json.dump({"L_ref_cd_m2": L_REF * k, "E_hall_lx": E_HALL, "res": RES, "samples": SAMPLES,
           "note": "яркость текстуры: L = L_ref · tex_linear (кд/м²); масштаб — средняя E на щитах пола = E_hall"},
          open(ROOT + "/godot/assets/lab/lab_room_bake.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("BAKE L_ref кд/м²", L_REF * k, flush=True)

# --- выгрузка: один материал с текстурой света, одна развёртка
M = bpy.data.materials.new("HALL_baked")
M.use_nodes = True
t = M.node_tree.nodes.new("ShaderNodeTexImage")
t.image = bpy.data.images.load(f"{TEXDIR}/lab_room_light.png")
bsdf = next(n for n in M.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
M.node_tree.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
hall.data.materials.clear()
hall.data.materials.append(M)
for p in hall.data.polygons:
    p.material_index = 0
hall.data.uv_layers.remove(hall.data.uv_layers[uv_src])
for o in list(coll.objects):
    if o is not hall:
        bpy.data.objects.remove(o)
bpy.ops.object.select_all(action="DESELECT")
hall.select_set(True)
bpy.ops.export_scene.gltf(filepath=GLB, export_format="GLB", use_selection=True, export_yup=True,
                          export_image_format="AUTO",
                          export_copyright="ROV-Sim, Kholopov E. G. (Холопов Е. Г.), 2026, CC BY 4.0")
print("BAKE glb", os.path.getsize(GLB) // 1024, "КБ", flush=True)
