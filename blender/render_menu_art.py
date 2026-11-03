"""Картинки главного меню из моделей проекта (запуск только в фоновом Blender, Cycles на процессоре:
Eevee в фоне на встроенной Radeon падает).

  blender -b -P blender/render_menu_art.py -- relief   <out.png>   рельеф места судна сверху, низкое солнце сбоку
                                                                    (тени как у гидролокатора бокового обзора), 30 × 30 м
  blender -b -P blender/render_menu_art.py -- lineart  <out.png>   контуры аппарата (Freestyle), вид 3/4, прозрачный фон

Палитру «медь» на рельеф накладывает work/tools/menu_sidescan.py. Габариты объектов для рамок целей
в меню (game/main_menu.gd, TARGETS) — из той же сцены, x и y в метрах, начало — центр места.
"""
import math
import sys

import bpy
from mathutils import Vector

ROOT = __file__.replace("\\", "/").rsplit("/blender/", 1)[0]
mode, out = sys.argv[sys.argv.index("--") + 1:][:2]
bpy.ops.wm.read_factory_settings(use_empty=True)
glb = ROOT + ("/godot/assets/wreck/wreck_site.glb" if mode == "relief" else "/godot/assets/rov/rov.glb")
bpy.ops.import_scene.gltf(filepath=glb)
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.device = "CPU"
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.type = "ORTHO"
sc.world = bpy.data.worlds.new("w")

if mode == "relief":
    sc.cycles.samples = 16
    sc.render.resolution_x = sc.render.resolution_y = 1400
    m = bpy.data.materials.new("white")
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (0.8, 0.8, 0.8, 1)
    b.inputs["Roughness"].default_value = 1.0
    sc.view_layers[0].material_override = m
    sc.world.use_nodes = True
    sc.world.node_tree.nodes["Background"].inputs[1].default_value = 0.02
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 6.0
    sun.data.angle = math.radians(1)
    sun.rotation_euler = (math.radians(90 - 12), 0, math.radians(90))   # солнце в 12° над дном, сбоку
    sc.collection.objects.link(sun)
    cam.data.ortho_scale = 30.0
    cam.data.clip_end = 200
    cam.location = (0, 0, 60)
else:
    sc.cycles.samples = 1
    sc.render.film_transparent = True
    sc.render.resolution_x, sc.render.resolution_y = 1800, 1000
    sc.render.use_freestyle = True
    sc.render.line_thickness_mode = "ABSOLUTE"
    sc.render.line_thickness = 1.6
    vl = sc.view_layers[0]
    hold = bpy.data.materials.new("hold")
    hold.use_nodes = True
    nt = hold.node_tree
    nt.nodes.clear()
    nt.links.new(nt.nodes.new("ShaderNodeHoldout").outputs[0], nt.nodes.new("ShaderNodeOutputMaterial").inputs[0])
    vl.material_override = hold
    fs = vl.freestyle_settings
    ls = fs.linesets[0] if fs.linesets else fs.linesets.new("L")
    ls.select_by_visibility = True
    ls.select_silhouette = ls.select_border = ls.select_crease = True
    ls.select_edge_mark = False
    fs.crease_angle = math.radians(140)
    if ls.linestyle is None:
        ls.linestyle = bpy.data.linestyles.new("LS")
    ls.linestyle.color = (0.86, 0.92, 0.96)
    ls.linestyle.thickness = 1.6
    pts = [o.matrix_world @ Vector(c) for o in sc.objects if o.type == "MESH" for c in o.bound_box]
    mn = Vector(map(min, *pts))
    mx = Vector(map(max, *pts))
    ctr, size = (mn + mx) / 2, max(mx - mn)
    cam.data.ortho_scale = size * 1.25
    d = Vector((1, 0.55, 0.9)).normalized()
    cam.location = ctr + d * size * 3
    cam.rotation_euler = (ctr - cam.location).to_track_quat("-Z", "Y").to_euler()
sc.render.filepath = out
bpy.ops.render.render(write_still=True)
