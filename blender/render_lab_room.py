"""«Сухие» рендеры зала над лабораторным бассейном (Cycles CPU): lab_room.blend + lab_pool.blend.

    blender -b --python blender/render_lab_room.py -- <папка> [вид ...]
Свет — трубки светильников (свечение + прямоугольные источники по их месту) и дневной свет окон.
Вода — только поверхность (стекло, n = 1,33): это вид, а не расчёт света в воде.
"""
import math
import os
import sys

import bpy
from mathutils import Vector

ROOT = "D:/Документы/ROV-Sim"
args = sys.argv[sys.argv.index("--") + 1:]
out, only = args[0], set(args[1:])
os.makedirs(out, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=ROOT + "/blender/lab_room.blend")
sc = bpy.context.scene
with bpy.data.libraries.load(ROOT + "/blender/lab_pool.blend") as (src, dst):
    dst.objects = list(src.objects)
for o in dst.objects:
    if o is not None and o.name not in ("cam", "top"):
        sc.collection.objects.link(o)
# прямоугольные источники у трубок (свечение само по себе в Cycles даёт много шума)
for o in [o for o in sc.objects if o.name.startswith("LampTube_") and o.name.endswith("a")]:
    ld = bpy.data.lights.new(o.name + "_L", "AREA")
    ld.shape = "RECTANGLE"
    ld.size, ld.size_y = 1.2, 0.12
    ld.energy = 45.0
    ld.color = (1.0, 0.97, 0.9)
    lo = bpy.data.objects.new(o.name + "_L", ld)
    sc.collection.objects.link(lo)
    lo.location = o.matrix_world.translation + Vector((0, 0, 2.62)) * 0 + Vector((0, 0, 0))
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
    sc.collection.objects.link(lo)
    lo.location = cen
    tgt = Vector((0.0, 0.0, 1.0))
    lo.rotation_euler = (tgt - cen).to_track_quat("-Z", "Y").to_euler()

bpy.ops.mesh.primitive_plane_add(size=3.5, location=(0, 0, 0))
w = bpy.context.active_object
mw = bpy.data.materials.new("water")
mw.use_nodes = True
b = next(n for n in mw.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
b.inputs["Base Color"].default_value = (0.55, 0.65, 0.45, 1)
b.inputs["Transmission Weight"].default_value = 1.0
b.inputs["IOR"].default_value = 1.33
b.inputs["Roughness"].default_value = 0.02
w.data.materials.append(mw)

sc.render.engine = "CYCLES"
sc.cycles.device = "CPU"
sc.cycles.samples = int(os.environ.get("ROOM_SAMPLES", "64"))
sc.cycles.use_denoising = True
sc.cycles.max_bounces = 6
sc.render.resolution_x, sc.render.resolution_y = 1280, 720
sc.render.image_settings.file_format = "PNG"
sc.view_settings.view_transform = "AgX"
sc.view_settings.exposure = float(os.environ.get("ROOM_EXPOSURE", "0.0"))
sc.world = bpy.data.worlds.new("w")
sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.0
cam = bpy.data.objects.new("cam_room", bpy.data.cameras.new("cam_room"))
sc.collection.objects.link(cam)
sc.camera = cam
HX, HY = -0.54, 0.505
views = [
    ("se", (3.3, -2.2, 1.65), (-1.2, 1.2, 0.9), 15),
    ("nw", (-2.4, 2.2, 1.65), (1.5, -1.5, 0.6), 15),
    ("hatch", (HX + 0.25, HY - 1.2, 1.55), (HX, HY, -0.3), 18),
    ("up", (HX, HY - 0.2, 0.06), (HX - 0.2, HY + 1.6, 1.8), 13),
    ("west", (-1.0, -1.2, 1.55), (-4.8, -0.8, 1.2), 15),
    ("center", (1.0, 1.6, 1.65), (-0.4, -0.5, 0.6), 18),
    ("cab_s", (-1.4, -1.0, 1.5), (-2.4, -3.0, 1.15), 18),
    ("dev_n", (-0.2, 1.55, 1.45), (-0.5, 2.6, 1.15), 22),
    ("dev_s", (1.3, -1.45, 1.45), (1.3, -2.6, 1.15), 22),
    ("dev_w", (-1.5, 1.4, 1.45), (-2.7, 1.6, 1.12), 22),
]
for name, loc, tgt, lens in views:
    if only and name not in only:
        continue
    cam.location = loc
    cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = lens
    sc.render.filepath = f"{out}/lab_room_{name}.png"
    bpy.ops.render.render(write_still=True)
    print("RENDER", name, flush=True)
