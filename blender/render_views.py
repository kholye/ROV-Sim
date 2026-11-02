"""Снимки модели для проверки (этап 3): собирает модель и рендерит виды в docs/model/.

Запуск без окна:
    blender -b --factory-startup --python blender/render_views.py
Вид сбоку ортогональный, со стороны правого борта, 1 px = 1 мм: его накладывает на фото
blender/overlay_photo.py. Сохраняет также blender/rov.blend.
"""
import math
import os

import bpy
from mathutils import Vector

ROOT = "D:/Документы/ROV-Sim"
OUT = ROOT + "/docs/model"
exec(open(ROOT + "/blender/build_rov.py", encoding="utf-8").read())

for ob in [o for o in bpy.data.objects if o.name in ("Cube", "Camera", "Light")]:
    bpy.data.objects.remove(ob, do_unlink=True)
for ob in list(COLL.all_objects):                     # внутренние цистерны на снимках не видны
    if ob.type == "MESH" and ob["internal"]:
        ob.hide_render = True

sc = bpy.context.scene
try:
    sc.render.engine = "BLENDER_WORKBENCH"
except TypeError as e:
    print(e)
sc.display.shading.light = "STUDIO"
sc.display.shading.color_type = "MATERIAL"
sc.display.shading.show_cavity = True
sc.render.film_transparent = True
sc.render.image_settings.file_format = "PNG"
sc.render.image_settings.color_mode = "RGBA"

cam_data = bpy.data.cameras.new("view")
cam = bpy.data.objects.new("view", cam_data)
sc.collection.objects.link(cam)
sc.camera = cam
os.makedirs(OUT, exist_ok=True)


def shot(name, eye, target, ortho=None, res=(1000, 700)):
    sc.render.resolution_x, sc.render.resolution_y = res
    cam.location = Vector(eye)
    d = Vector(target) - cam.location
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    if ortho:
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = ortho
    else:
        cam_data.type = "PERSP"
        cam_data.lens = 50
    sc.render.filepath = f"{OUT}/{name}.png"
    bpy.ops.render.render(write_still=True)


# Blender: X вправо, Y вперёд, Z вверх. Правый борт = +X.
shot("side_ortho_1mm", (2, 0, 0), (0, 0, 0), ortho=1.0, res=(1000, 500))   # 1000 px на 1 м
shot("top_ortho", (0, 0, 2), (0, 0, 0), ortho=1.0, res=(500, 1000))      # нос вверху кадра
shot("front_ortho", (0, 2, 0), (0, 0, 0), ortho=0.5, res=(500, 500))
# Силуэты для сопротивления (physics_ref/verify/model_properties.py), 1 px = 1 мм.
# Плоскости убраны с вида сверху: их сопротивление считает отдельная модель плоскостей.
for n in ("fin_L", "fin_R"):
    bpy.data.objects[n].hide_render = True
shot("top_nofins_1mm", (0, 0, 2), (0, 0, 0), ortho=1.0, res=(500, 1000))
for n in ("fin_L", "fin_R"):
    bpy.data.objects[n].hide_render = False
shot("three_quarter", (1.0, 1.1, 0.55), (0, 0.02, -0.03), res=(1200, 800))
shot("three_quarter_stern", (0.9, -1.1, 0.4), (0, -0.02, -0.03), res=(1200, 800))
shot("closeup_nose", (0.35, 0.75, 0.12), (0, 0.36, -0.05), res=(1000, 750))
shot("closeup_thruster", (0.45, -0.55, 0.12), (0.11, -0.25, 0), res=(1000, 750))

bpy.data.objects.remove(cam, do_unlink=True)
bpy.ops.wm.save_as_mainfile(filepath=ROOT + "/blender/rov.blend")
