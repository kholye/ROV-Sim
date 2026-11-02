"""Осмотр скана судна (только чтение): размеры, сетки, текстуры, превью с 4 сторон.
blender -b --factory-startup --python blender/inspect_scan.py -- <scene.gltf> <папка превью>
"""
import math
import sys

import bpy
from mathutils import Vector

src, out = sys.argv[sys.argv.index("--") + 1:][:2]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
print("SCAN objects", [(o.name, len(o.data.polygons)) for o in meshes])
print("SCAN bbox", tuple(round(v, 3) for v in lo), tuple(round(v, 3) for v in hi), "size", tuple(round(v, 3) for v in hi - lo))
for im in bpy.data.images:
    print("SCAN image", im.name, im.size[:])
# превью: Workbench с текстурой
sc = bpy.context.scene
sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.light = "STUDIO"
sc.display.shading.color_type = "TEXTURE"
sc.render.resolution_x, sc.render.resolution_y = 960, 540
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
sc.camera = cam
c = (lo + hi) / 2
r = (hi - lo).length * 0.9
for k, az in enumerate([30, 120, 210, 300]):
    a = math.radians(az)
    cam.location = c + Vector((r * math.cos(a), r * math.sin(a), r * 0.45))
    cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = f"{out}/scan_{k}.png"
    bpy.ops.render.render(write_still=True)
