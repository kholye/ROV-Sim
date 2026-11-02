"""Сборка модели аппарата в Blender (этап 3, вторая версия: фаски, детали, материалы).

Запуск без окна (рекомендуется):
    blender -b --factory-startup --python blender/render_views.py
или внутри Blender: exec(open(r"D:/Документы/ROV-Sim/blender/build_rov.py", encoding="utf-8").read())

Скрипт удаляет коллекции ROV и ROV_cutters, строит модель заново, пишет отчёт
blender/rov_report.json и экспортирует godot/assets/rov/rov.glb. Размеры: docs/model.md.

Оси. Размеры заданы в системе тела Fossen (NED: x вперёд, y вправо, z вниз), начало
координат = центр габарита 650 мм на оси главной трубы, как в rov_params.json (cb = 0).
В Blender: X = y_ned (вправо), Y = x_ned (вперёд), Z = -z_ned (вверх). Экспортёр glTF
переводит это в Godot как (y, -z, -x), то есть ровно как NedGodot.vec(): вперёд = -Z.

Приёмы: живые
модификаторы Boolean -> Bevel (по углу 30°) -> Weighted Normal, применяются при экспорте;
одинаковые болты делят один меш; материалы MAT_*.
"""
import json
import math
import os

import bmesh
import bpy
from mathutils import Matrix, Vector

ROOT = "D:/Документы/ROV-Sim"
PARAMS = ROOT + "/godot/physics/rov_params.json"
GLB = ROOT + "/godot/assets/rov/rov.glb"
REPORT = ROOT + "/blender/rov_report.json"

SEG = 32       # сегменты крупных цилиндров
SEG_C = 24     # хомуты, насадки
SEG_M = 16     # средних
SEG_S = 10     # мелких
SHARP = math.radians(30)


def B(x, y, z):
    """NED-точка тела -> координаты Blender."""
    return Vector((y, x, -z))


# ---------- материалы ----------
# (цвет, metallic, roughness, emission, alpha). Значения по таблице PBR навыка materials.
MATS = {
    "MAT_Paint_Yellow": ((0.95, 0.76, 0.02), 0.0, 0.40, 0, 1),     # окрашенный ПВХ
    "MAT_Plastic_Green": ((0.40, 0.88, 0.04), 0.0, 0.50, 0, 1),    # насадки ApisQueen
    "MAT_Steel_Galvanized": ((0.72, 0.72, 0.74), 1.0, 0.35, 0, 1), # хомуты, пластина
    "MAT_Steel_Shot": ((0.45, 0.45, 0.47), 1.0, 0.30, 0, 1),       # дробь в гильзах
    "MAT_Rubber_Orange": ((0.90, 0.33, 0.04), 0.0, 0.80, 0, 1),    # прокладки хомутов
    "MAT_Plastic_Black": ((0.025, 0.025, 0.025), 0.0, 0.55, 0, 1),
    "MAT_Connector_Blue": ((0.04, 0.16, 0.55), 0.0, 0.45, 0, 1),   # гермовводы
    "MAT_Textolite_Orange": ((0.65, 0.30, 0.12), 0.0, 0.55, 0, 1), # кормовая крышка
    "MAT_Prop_Red": ((0.45, 0.08, 0.06), 0.0, 0.40, 0, 1),         # винт
    "MAT_PCB_Green": ((0.04, 0.30, 0.10), 0.0, 0.50, 0, 1),
    "MAT_Emissive_LED": ((1.0, 0.92, 0.75), 0.0, 0.30, 4.0, 1),
    "MAT_Glass_Clear": ((0.85, 0.90, 0.95), 0.0, 0.05, 0, 0.25),   # бокс камеры
    "MAT_Internal_Tank": ((0.20, 0.40, 0.90), 0.0, 0.50, 0, 1),
}


def material(name):
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
        m.use_nodes = True
    col, met, rough, emit, alpha = MATS[name]
    bsdf = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*col, 1)
    bsdf.inputs["Metallic"].default_value = met
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Alpha"].default_value = alpha
    if emit:
        bsdf.inputs["Emission Color"].default_value = (*col, 1)
        bsdf.inputs["Emission Strength"].default_value = emit
    if alpha < 1:
        try:
            m.surface_render_method = "BLENDED"
        except (AttributeError, TypeError):
            m.blend_method = "BLEND"
    m.diffuse_color = (*col, alpha)
    return m


# ---------- построение ----------
COLL = None
CUT = None


def mark_sharp(bm):
    """Гладкая заливка, рёбра острее 30° жёсткие (их и скругляет Bevel)."""
    bm.normal_update()
    for f in bm.faces:
        f.smooth = True
    for e in bm.edges:
        if len(e.link_faces) == 2 and e.calc_face_angle(0) > SHARP:
            e.smooth = False


def new_object(name, bm, mats, origin_ned=(0, 0, 0), parent=None, role="", internal=False,
               bevel=None, cutter=None, mesh=None, in_volume=True):
    """bm задан в координатах Blender относительно origin_ned.
    mats: имя материала или список (индекс = face.material_index).
    bevel: (ширина, сегменты) или None. cutter: объект для Boolean Difference.
    mesh: готовый меш (общий для копий), тогда bm = None."""
    if mesh is None:
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
        bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-6)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        mark_sharp(bm)
        mesh = bpy.data.meshes.new(name)
        bm.to_mesh(mesh)
        bm.free()
        for m in [mats] if isinstance(mats, str) else mats:
            mesh.materials.append(material(m))
    ob = bpy.data.objects.new(name, mesh)
    COLL.objects.link(ob)
    bpy.context.view_layer.update()            # иначе matrix_world нового родителя = единица
    ob.location = B(*origin_ned)
    if parent is not None:
        ob.parent = parent
        ob.location = B(*origin_ned) - parent.matrix_world.translation
    if cutter is not None:
        mod = ob.modifiers.new("Boolean", "BOOLEAN")
        mod.operation = "DIFFERENCE"
        mod.solver = "EXACT"
        mod.object = cutter
    if bevel:
        mod = ob.modifiers.new("Bevel", "BEVEL")
        mod.width, mod.segments = bevel
        mod.limit_method = "ANGLE"
        mod.angle_limit = SHARP
        mod.harden_normals = True
        mod = ob.modifiers.new("WeightedNormal", "WEIGHTED_NORMAL")
        mod.keep_sharp = True
    ob["role"] = role
    ob["internal"] = internal
    ob["in_volume"] = in_volume and not internal     # входит в вытесненный объём
    return ob


def merge(dst, src):
    """Добавить геометрию bmesh src в dst (src освобождается)."""
    tmp = bpy.data.meshes.new("tmp")
    src.to_mesh(tmp)
    dst.from_mesh(tmp)
    bpy.data.meshes.remove(tmp)
    src.free()
    return dst


def lathe(prof, seg=SEG, closed=False):
    """Тело вращения вокруг оси x_ned. prof: [(x, r)] в метрах."""
    bm = bmesh.new()
    vs = [bm.verts.new(B(px, 0, -pr)) for px, pr in prof]
    es = [bm.edges.new((vs[i], vs[i + 1])) for i in range(len(vs) - 1)]
    if closed:
        es.append(bm.edges.new((vs[-1], vs[0])))
    bmesh.ops.spin(bm, geom=vs + es, cent=(0, 0, 0), axis=(0, 1, 0),
                   angle=2 * math.pi, steps=seg, use_merge=True)
    return bm


def cyl(x0, x1, r, seg=SEG):
    return lathe([(x0, 0), (x0, r), (x1, r), (x1, 0)], seg)


def ring(x0, x1, r_in, r_out, seg=SEG):
    return lathe([(x0, r_in), (x0, r_out), (x1, r_out), (x1, r_in)], seg, closed=True)


def box(x0, x1, y0, y1, z0, z1, bm=None):
    """Брусок в NED-пределах (относительно начала объекта)."""
    bm = bm or bmesh.new()
    res = bmesh.ops.create_cube(bm, size=1.0)
    lo, hi = B(x0, y0, z1), B(x1, y1, z0)
    c = (lo + hi) / 2
    s = Vector((abs(hi.x - lo.x), abs(hi.y - lo.y), abs(hi.z - lo.z)))
    bmesh.ops.transform(bm, verts=res["verts"],
                        matrix=Matrix.Translation(c) @ Matrix.Diagonal(s.to_4d()))
    return bm


def vcyl(r, h, seg=SEG_S, z0=0.0):
    """Цилиндр вдоль оси z_ned (вниз) от z0 до z0 + h."""
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r, radius2=r, depth=h,
                          matrix=Matrix.Translation(B(0, 0, z0 + h / 2)))
    return bm


def rotate_x(bm, ang):
    """Поворот вокруг оси x_ned (продольной) на ang, положительно = от +y к +z."""
    bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(ang, 3, "Y"))
    return bm


def fin(side):
    """Носовая плоскость: трапеция в плоскости z = 0 по fins[0] из rov_params.json."""
    s = 1 if side == "R" else -1
    pts = [(0.090, 0.055), (0.290, 0.055), (0.2615, 0.125), (0.1185, 0.125)]
    t = 0.0015
    bm = bmesh.new()
    bot = [bm.verts.new(B(x, s * y, t)) for x, y in pts]
    top = [bm.verts.new(B(x, s * y, -t)) for x, y in pts]
    bm.faces.new(bot)
    bm.faces.new(top[::-1])
    for i in range(4):
        j = (i + 1) % 4
        bm.faces.new((bot[i], bot[j], top[j], top[i]))
    return bm


def blade_bm(pitch=0.04):
    """Лопасть винта: прямоугольные сечения с круткой по шагу pitch (м/об)."""
    st = [(0.0085, 0.008), (0.013, 0.013), (0.017, 0.015), (0.021, 0.013), (0.0245, 0.008)]
    t = 0.0012
    bm = bmesh.new()
    rings = []
    for r, c in st:
        beta = math.atan2(pitch, 2 * math.pi * r)         # угол установки сечения
        ch = Vector((math.cos(beta), math.sin(beta)))      # (касательная, ось)
        th = Vector((-math.sin(beta), math.cos(beta)))
        quad = []
        for a, b in ((-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)):
            p = ch * (a * c) + th * (b * t)
            quad.append(bm.verts.new((p.x, p.y, r)))       # Blender: X касат., Y ось, Z радиус
        rings.append(quad)
    for q0, q1 in zip(rings, rings[1:]):
        for i in range(4):
            j = (i + 1) % 4
            bm.faces.new((q0[i], q0[j], q1[j], q1[i]))
    bm.faces.new(rings[0][::-1])
    bm.faces.new(rings[-1])
    return bm


def thruster(side, pos):
    """Движитель: насадка Ø62 × 75 мм (Дунаев 1.5.1) с прорезями, мотор, 4 лопасти,
    передняя крестовина, кронштейн к хомуту."""
    tag = "thruster_" + side
    root = bpy.data.objects.new(tag, None)
    root.empty_display_type = "ARROWS"
    root.empty_display_size = 0.03
    COLL.objects.link(root)
    root.location = B(*pos)
    root.parent = ROV
    root["role"] = "движитель: точка приложения тяги (thruster_pos), тяга вдоль +x тела"
    L, ro, ri = 0.075, 0.031, 0.027
    # прорези в насадке: 8 штук по кругу в передней половине
    cut = bmesh.new()
    for k in range(8):
        merge(cut, rotate_x(box(0.004, 0.020, -0.0045, 0.0045, -0.040, -0.024),
                            k * math.pi / 4 + math.pi / 8))
    cutter = bpy.data.objects.new(tag + "_cutter", bpy.data.meshes.new(tag + "_cutter"))
    cut.to_mesh(cutter.data)
    cut.free()
    CUT.objects.link(cutter)
    cutter.location = B(*pos)
    cutter.display_type = "WIRE"
    cutter.hide_render = True
    duct = lathe([(-L / 2, ri), (-L / 2, ro - 0.001), (-L / 2 + 0.003, ro), (L / 2 - 0.004, ro),
                  (L / 2, ro - 0.002), (L / 2, ri + 0.001), (L / 2 - 0.006, ri)], SEG_C,
                 closed=True)
    new_object(tag + "_duct", duct, "MAT_Plastic_Green", pos, root,
               "насадка движителя (fins: насадка)", bevel=(0.0008, 1), cutter=cutter)
    # мотор (спереди) и обтекатель винта (сзади)
    hub = lathe([(0.030, 0), (0.030, 0.010), (0.026, 0.012), (-0.002, 0.012),
                 (-0.002, 0)], SEG_M)
    for k in range(4):                                   # крестовина к насадке спереди
        merge(hub, rotate_x(box(0.026, 0.032, -0.002, 0.002, -(ri + 0.0005), -0.010),
                            k * math.pi / 2 + math.pi / 4))
    new_object(tag + "_hub", hub, "MAT_Plastic_Black", pos, root, "мотор и крестовина",
               bevel=(0.0008, 1))
    prop = lathe([(-0.002, 0), (-0.002, 0.0115), (-0.010, 0.009), (-0.016, 0.004),
                  (-0.018, 0)], SEG_M)                    # обтекатель вращается с винтом
    for k in range(4):
        b = blade_bm()
        bmesh.ops.translate(b, verts=b.verts, vec=B(-0.008, 0, 0))
        merge(prop, rotate_x(b, k * math.pi / 2))
    new_object(tag + "_prop", prop, "MAT_Prop_Red", pos, root,
               "винт (вращать вокруг оси x тела)")
    # кронштейн от хомута на корпусе до насадки: полоса с отгибом
    s = 1 if side == "R" else -1
    y_band = math.sqrt(0.0595 ** 2 - pos[2] ** 2) - 0.001  # лента хомута на высоте движителя
    y0, y1 = sorted((s * y_band, s * (abs(pos[1]) - ro + 0.001)))
    br = box(-0.010, 0.010, y0 - pos[1], y1 - pos[1], -0.004, 0.004)
    new_object(tag + "_bracket", br, "MAT_Steel_Galvanized", pos, root, "кронштейн",
               bevel=(0.001, 1))


def marker(name, ned, role, size=0.04, shape="SPHERE", extra=None):
    e = bpy.data.objects.new(name, None)
    e.empty_display_type = shape
    e.empty_display_size = size
    COLL.objects.link(e)
    e.location = B(*ned)
    e.parent = ROV
    e["role"] = role
    for k, v in (extra or {}).items():
        e[k] = v
    return e


# Общие меши для повторяющихся деталей (instancing: одна геометрия на все копии)
SHARED = {}


def shared(key, make, mats):
    if key not in SHARED:
        bm = make()
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
        bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-6)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        mark_sharp(bm)
        me = bpy.data.meshes.new(key)
        bm.to_mesh(me)
        bm.free()
        for m in [mats] if isinstance(mats, str) else mats:
            me.materials.append(material(m))
        SHARED[key] = me
    return SHARED[key]


def hex_bolt_x():
    """Болт с шестигранной головкой и шайбой вдоль -x (головка торчит назад), M6."""
    bm = lathe([(0, 0), (0, 0.0065), (-0.0012, 0.0065), (-0.0012, 0)], SEG_S)
    merge(bm, lathe([(-0.0012, 0), (-0.0012, 0.0058), (-0.0052, 0.0058), (-0.0052, 0)], 6))
    return bm


def clamp_bolt():
    """Болт ушек хомута M6 с головкой и гайкой; ось вдоль z_ned (сквозь ушки)."""
    bm = vcyl(0.003, 0.020, SEG_S, -0.010)
    merge(bm, vcyl(0.0055, 0.004, 6, -0.0095))           # головка сверху
    merge(bm, vcyl(0.0055, 0.005, 6, 0.0055))            # гайка снизу
    return bm


def gland():
    """Гермоввод: синяя гайка-шестигранник + чёрный корпус, ось вдоль -x."""
    bm = lathe([(0, 0), (0, 0.0075), (-0.008, 0.0075), (-0.008, 0)], 6)
    for f in bm.faces:
        f.material_index = 0
    body = lathe([(-0.008, 0), (-0.008, 0.0062), (-0.026, 0.0055), (-0.030, 0.003),
                  (-0.030, 0)], SEG_S)
    for f in body.faces:
        f.material_index = 1
    return merge(bm, body)


def pipe_clamp(name, x, r, lugs_angle, width=0.014, extra_bolt=False):
    """Трубный хомут: стальная лента на оранжевой прокладке, ушки с болтом с двух сторон.
    lugs_angle: угол ушек от +y к +z (0 = по бортам, pi/2 = сверху-снизу)."""
    band = ring(x - width / 2, x + width / 2, r + 0.0015, r + 0.0045, SEG_C)
    for sgn in (1, -1):
        for dz in (-0.004, 0.004):                       # два ушка с зазором 4 мм под болт
            lug = box(x - width / 2, x + width / 2, sgn * (r + 0.004), sgn * (r + 0.016),
                      dz - 0.0015, dz + 0.0015)
            merge(band, rotate_x(lug, lugs_angle))
    ob = new_object(name, band, "MAT_Steel_Galvanized", parent=ROV, role="хомут")
    liner = ring(x - width / 2 - 0.0015, x + width / 2 + 0.0015, r, r + 0.0015, SEG_C)
    new_object(name + "_liner", liner, "MAT_Rubber_Orange", parent=ROV,
               role="резиновая прокладка хомута")
    me = shared("clamp_bolt", clamp_bolt, "MAT_Steel_Galvanized")
    for sgn in (1, -1):
        c = Matrix.Rotation(lugs_angle, 3, "Y") @ B(x, sgn * (r + 0.011), 0)
        b = bpy.data.objects.new(f"{name}_bolt_{'R' if sgn > 0 else 'L'}", me)
        COLL.objects.link(b)
        b.parent = ROV
        b.location = c
        b.rotation_euler = (0, lugs_angle, 0)
        b["role"] = "болт хомута"
        b["internal"] = False
    return ob


# ---------- сцена ----------
for cname in ("ROV", "ROV_cutters"):
    old = bpy.data.collections.get(cname)
    if old:
        for ob in list(old.all_objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        bpy.data.collections.remove(old)
for me in [m for m in bpy.data.meshes if m.users == 0]:
    bpy.data.meshes.remove(me)
COLL = bpy.data.collections.new("ROV")
bpy.context.scene.collection.children.link(COLL)
CUT = bpy.data.collections.new("ROV_cutters")
bpy.context.scene.collection.children.link(CUT)
bpy.context.scene.unit_settings.system = "METRIC"
bpy.context.scene.unit_settings.scale_length = 1.0

params = json.load(open(PARAMS, encoding="utf-8"))
P = {k: v["value"] for k, v in params.items() if isinstance(v, dict) and "value" in v}

ROV = bpy.data.objects.new("ROV", None)
ROV.empty_display_type = "PLAIN_AXES"
ROV["role"] = "начало системы тела (NED): центр габарита 650 мм на оси главной трубы"
COLL.objects.link(ROV)

# ===== Корпус: габарит 650 мм от кормового фланца до носового колпака =====
new_object("hull_stern_flange",
           lathe([(-0.300, 0), (-0.300, 0.070), (-0.325, 0.070), (-0.325, 0.046),
                  (-0.318, 0.046), (-0.318, 0)]),
           "MAT_Paint_Yellow", parent=ROV, role="кормовой фланец Ø140 с углублением под крышку",
           bevel=(0.0025, 2))
new_object("stern_endplate", cyl(-0.320, -0.318, 0.046), "MAT_Textolite_Orange", parent=ROV,
           role="кормовая крышка с гермовводами")
new_object("hull_main_tube", cyl(-0.300, 0.255, 0.055), "MAT_Paint_Yellow", parent=ROV,
           role="главная труба Ø110 (ПВХ 110)", bevel=(0.0015, 1))
new_object("hull_nose_cap",
           lathe([(0.255, 0), (0.255, 0.060), (0.275, 0.060), (0.275, 0.070),
                  (0.325, 0.070), (0.325, 0.017), (0.312, 0.017), (0.312, 0)]),
           "MAT_Paint_Yellow", parent=ROV, role="носовой колпак Ø140 с гнездом разъёма камеры",
           bevel=(0.003, 2))
new_object("hull_stern_collar", ring(-0.295, -0.265, 0.055, 0.0605, SEG_C),
           "MAT_Steel_Galvanized", parent=ROV, role="стяжной хомут кормового фланца")
# болты кормового фланца: 8 шт. на r = 58 мм, головки назад
me = shared("flange_bolt", hex_bolt_x, "MAT_Steel_Galvanized")
for k in range(8):
    a = k * math.pi / 4 + math.pi / 8
    b = bpy.data.objects.new(f"stern_bolt_{k + 1}", me)
    COLL.objects.link(b)
    b.parent = ROV
    b.location = B(-0.325, 0.058 * math.cos(a), 0.058 * math.sin(a))
    b["role"], b["internal"] = "болт фланца", False
# гермовводы на кормовой крышке
me = shared("gland", gland, ["MAT_Connector_Blue", "MAT_Plastic_Black"])
for i, (cy, cz) in enumerate(((-0.022, -0.020), (0.0, -0.028), (0.022, -0.020),
                              (-0.026, 0.008), (0.026, 0.008), (0.0, 0.024))):
    g = bpy.data.objects.new(f"stern_connector_{i + 1}", me)
    COLL.objects.link(g)
    g.parent = ROV
    g.location = B(-0.320, cy, cz)
    g["role"], g["internal"] = "гермоввод", False
# хомуты главной трубы (x по фото); у хомута движителей ушки сверху-снизу
pipe_clamp("clamp_thrusters", -0.250, 0.055, math.pi / 2)
for i, x in enumerate((-0.190, 0.021, 0.165, 0.246)):
    pipe_clamp(f"clamp_{i + 1}", x, 0.055, 0.0)

# ===== Нижняя труба (энергоотсек): ось на 85 мм ниже =====
ZL = 0.085
new_object("lower_flange", cyl(-0.250, -0.230, 0.030), "MAT_Paint_Yellow", (0, 0, ZL), ROV,
           "фланец нижней трубы Ø60", bevel=(0.002, 2))
new_object("lower_tube", cyl(-0.230, 0.180, 0.020), "MAT_Paint_Yellow", (0, 0, ZL), ROV,
           "нижняя труба (энергоотсек, батарея) Ø40", bevel=(0.001, 1))
new_object("lower_cap", cyl(0.180, 0.205, 0.026), "MAT_Paint_Yellow", (0, 0, ZL), ROV,
           "заглушка нижней трубы Ø52", bevel=(0.002, 2))
new_object("lower_gland", gland(), ["MAT_Connector_Blue", "MAT_Plastic_Black"],
           (-0.250, 0, ZL), ROV, "гермоввод энергоотсека")
for i, x in enumerate((0.044, 0.165)):
    new_object(f"lower_clamp_{i + 1}", ring(x - 0.007, x + 0.007, 0.0215, 0.0245, SEG_M),
               "MAT_Steel_Galvanized", (0, 0, ZL), ROV, "хомут нижней трубы",
               bevel=(0.0006, 1))
    new_object(f"lower_clamp_{i + 1}_liner", ring(x - 0.0085, x + 0.0085, 0.020, 0.0215, SEG_M),
               "MAT_Rubber_Orange", (0, 0, ZL), ROV, "прокладка")


def ballast(name, x0, x1, origin, parent, role):
    """Гильза с дробью Ø35: сетчатая трубка (сталь) с чёрной пробкой и двумя стяжками."""
    g = cyl(x0, x1 - 0.012, 0.0175, SEG_M)
    ob = new_object(name, g, "MAT_Steel_Shot", origin, parent, role, bevel=(0.0015, 1))
    new_object(name + "_plug", cyl(x1 - 0.012, x1, 0.0170, SEG_M), "MAT_Plastic_Black",
               origin, parent, "пробка гильзы", bevel=(0.0015, 1))
    for t, xt in enumerate((x0 + 0.25 * (x1 - x0), x0 + 0.70 * (x1 - x0))):
        new_object(f"{name}_tie_{t + 1}", ring(xt - 0.002, xt + 0.002, 0.0175, 0.0188, SEG_M),
                   "MAT_Plastic_Black", origin, parent, "стяжка")
    return ob


# ===== Балласт (2 кг, 1 кг сбрасывается) =====
zb = ZL + 0.020 + 0.0175
ballast("ballast_rear", -0.205, -0.075, (0, 0, zb), ROV, "неотделяемый груз (дробь)")
mag = vcyl(0.0175, 0.025, SEG_M)
new_object("magnet", mag, "MAT_Steel_Galvanized", (0.044, 0, ZL + 0.020 + 0.0005), ROV,
           "электромагнит аварийного сброса", bevel=(0.0015, 1))
drop = bpy.data.objects.new("ballast_drop", None)
drop.empty_display_type = "CUBE"
drop.empty_display_size = 0.01
COLL.objects.link(drop)
drop.location = B(0.044, 0, ZL + 0.020 + 0.0255)
drop.parent = ROV
drop["role"] = "сбрасываемый груз 1 кг (команда G/A): отцепить этот узел целиком"
z0 = ZL + 0.020 + 0.0255
new_object("ballast_drop_bar", box(-0.105, 0.085, -0.0125, 0.0125, 0, 0.002),
           "MAT_Steel_Galvanized", (0.044, 0, z0), drop, "якорь электромагнита",
           bevel=(0.0006, 1))
ballast("ballast_drop_shot", -0.065, 0.065, (0.044, 0, z0 + 0.002 + 0.0175), drop,
        "сбрасываемая гильза с дробью")

# ===== Носовая пластина, камера, лампа =====
new_object("nose_plate", box(0.210, 0.400, -0.030, 0.030, 0.071, 0.073),
           "MAT_Steel_Galvanized", parent=ROV, role="алюминиевая пластина под носом",
           bevel=(0.0006, 1))
ballast("ballast_front", 0.210, 0.300, (0, 0, 0.073 + 0.0175), ROV,
        "неотделяемый груз под пластиной")
nc = new_object("nose_connector", gland(), ["MAT_Connector_Blue", "MAT_Plastic_Black"],
                (0.313, 0, 0), ROV, "разъём кабеля камеры (от колпака к боксу)")
nc.rotation_euler = (0, 0, math.pi)                     # корпусом вперёд, к камере
# камера: прозрачный бокс, внутри корпус камеры, спереди рамка и объектив
cam = new_object("camera", box(0.335, 0.380, -0.0325, 0.0325, -0.025, 0.025),
                 "MAT_Glass_Clear", parent=ROV, role="камера Digma DiCam 300 в боксе",
                 bevel=(0.004, 2))
new_object("camera_body", box(0.339, 0.373, -0.029, 0.029, -0.021, 0.021),
           "MAT_Plastic_Black", parent=ROV, role="корпус камеры внутри бокса", bevel=(0.002, 1),
           in_volume=False)                       # внутри бокса: объём бокса уже учтён
new_object("camera_frame", box(0.380, 0.384, -0.030, 0.030, -0.023, 0.023), "MAT_Plastic_Black",
           parent=ROV, role="передняя рамка бокса", bevel=(0.0015, 1))
new_object("camera_lens", lathe([(0.384, 0), (0.384, 0.016), (0.392, 0.015), (0.393, 0.012),
                                 (0.391, 0.011), (0.391, 0)], SEG_M),
           "MAT_Plastic_Black", parent=ROV, role="объектив", bevel=(0.0006, 1))
new_object("camera_latch", box(0.347, 0.373, -0.024, 0.024, -0.033, -0.025), "MAT_Plastic_Black",
           parent=ROV, role="защёлка бокса", bevel=(0.0015, 1))
for i, xb in enumerate((0.349, 0.363)):
    btn = bmesh.new()
    bmesh.ops.create_cone(btn, cap_ends=True, segments=SEG_S, radius1=0.004, radius2=0.004,
                          depth=0.004, matrix=Matrix.Rotation(math.pi / 2, 4, "Y"))
    new_object(f"camera_button_{i + 1}", btn, "MAT_Steel_Galvanized", (xb, 0.0345, -0.004),
               ROV, "кнопка бокса")
new_object("camera_mount", box(0.348, 0.368, -0.010, 0.010, 0.025, 0.071), "MAT_Plastic_Black",
           parent=ROV, role="крепление камеры", bevel=(0.001, 1))
# лампа: чёрный бокс с углублённой панелью (плата + 9 светодиодов 3 × 3)
lamp = box(0.300, 0.333, -0.025, 0.025, 0.073, 0.118)
front = max(lamp.faces, key=lambda f: f.calc_center_median().y)
res = bmesh.ops.inset_individual(lamp, faces=[front], thickness=0.003)
bmesh.ops.translate(lamp, verts=front.verts, vec=(0, -0.004, 0))
front.material_index = 1
new_object("lamp", lamp, ["MAT_Plastic_Black", "MAT_PCB_Green"], parent=ROV,
           role="бокс лампы, 9 светодиодов 5000 K, 120°", bevel=(0.0012, 1))
leds = bmesh.new()
for iy in (-1, 0, 1):
    for iz in (-1, 0, 1):
        merge(leds, box(0.329, 0.3305, iy * 0.012 - 0.0035, iy * 0.012 + 0.0035,
                        0.0955 + iz * 0.012 - 0.0025, 0.0955 + iz * 0.012 + 0.0025))
new_object("lamp_leds", leds, "MAT_Emissive_LED", parent=ROV, role="светодиоды лампы")

# ===== Плоскости (по fins[0] rov_params.json) =====
new_object("fin_L", fin("L"), "MAT_Paint_Yellow", parent=ROV, role="носовая плоскость, левая",
           bevel=(0.0008, 1))
new_object("fin_R", fin("R"), "MAT_Paint_Yellow", parent=ROV, role="носовая плоскость, правая",
           bevel=(0.0008, 1))

# ===== Движители (thruster_pos) =====
tp = P["thruster_pos"]
thruster("L", (tp[0], -tp[1], tp[2]))
thruster("R", (tp[0], tp[1], tp[2]))


# ===== Кабели: от кормовых гермовводов к движителям =====
def cable(name, pts_ned, r=0.0024):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = r
    cu.bevel_resolution = 1
    cu.resolution_u = 6
    cu.use_fill_caps = True
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(len(pts_ned) - 1)
    for bp, p in zip(sp.bezier_points, pts_ned):
        bp.co = B(*p)
        bp.handle_left_type = bp.handle_right_type = "AUTO"
    tmp = bpy.data.objects.new("tmp_curve", cu)
    COLL.objects.link(tmp)
    bpy.context.view_layer.update()
    me = bpy.data.meshes.new_from_object(tmp.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    bpy.data.objects.remove(tmp, do_unlink=True)
    bpy.data.curves.remove(cu)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bm.to_mesh(me)
    bm.free()
    me.materials.clear()
    me.materials.append(material("MAT_Plastic_Black"))
    for poly in me.polygons:
        poly.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    COLL.objects.link(ob)
    ob.parent = ROV
    ob["role"], ob["internal"] = "кабель", False
    return ob


for s, tag in ((1, "R"), (-1, "L")):
    cable(f"cable_thruster_{tag}", [(-0.348, s * 0.026, 0.008), (-0.362, s * 0.060, 0.0),
                                    (-0.338, s * 0.085, 0.004), (-0.300, s * 0.082, 0.020),
                                    (-0.262, s * 0.079, tp[2])])

# ===== Цистерны (внутри корпуса): 70 мл, Ø40 × 56 мм, x по tank_x =====
for name, x in (("tank_bow", P["tank_x"][0]), ("tank_stern", P["tank_x"][1])):
    new_object(name, cyl(-0.028, 0.028, 0.020, SEG_M), "MAT_Internal_Tank", (x, 0, 0), ROV,
               "поршневая цистерна 70 мл (внутри корпуса)", internal=True)

# ===== Метки =====
marker("CG", P["cg_dry"], "центр масс (cg_dry из rov_params.json)", 0.03, "SPHERE")
marker("CB", P["cb"], "центр плавучести (cb из rov_params.json)", 0.03, "CIRCLE")
marker("camera_eye", (0.393, 0, 0), "точка камеры: Camera3D, смотрит вдоль -Z (вперёд)", 0.02,
       "SINGLE_ARROW")
marker("lamp_emitter", (0.3305, 0, 0.0955), "точка лампы: SpotLight3D 120°, вдоль -Z", 0.02,
       "SINGLE_ARROW")
bpy.context.view_layer.update()


# ---------- отчёт (по геометрии после модификаторов) ----------
DG = bpy.context.evaluated_depsgraph_get()


def mesh_stats(ob):
    ev = ob.evaluated_get(DG)
    me = ev.to_mesh()
    bm = bmesh.new()
    bm.from_mesh(me)
    ev.to_mesh_clear()
    bm.transform(ob.matrix_world)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    vol, c = 0.0, Vector()
    for f in bm.faces:
        a, b, d = (v.co for v in f.verts)
        v6 = a.dot(b.cross(d))
        vol += v6
        c += v6 * (a + b + d) / 4
    tris = len(bm.faces)
    manifold = all(e.is_manifold for e in bm.edges)
    xs = [v.co.copy() for v in bm.verts]
    bm.free()
    vol /= 6
    c = c / (6 * vol) if vol else c
    return tris, vol, c, manifold, xs


def ned(v):
    return [round(v.y, 5), round(v.x, 5), round(-v.z, 5)]


rep = {"parts": {}, "tris_total": 0, "objects": 0, "materials": sorted(MATS)}
disp, mom = 0.0, Vector()
hull_pts = []
all_pts = []
for ob in list(COLL.all_objects):
    if ob.type != "MESH":
        continue
    tris, vol, c, man, pts = mesh_stats(ob)
    internal = bool(ob.get("internal", False))
    rep["parts"][ob.name] = {"tris": tris, "volume_l": round(vol * 1e3, 4), "manifold": man,
                             "internal": internal, "centroid_ned_m": ned(c)}
    rep["tris_total"] += tris
    rep["objects"] += 1
    all_pts += pts
    if ob.name.startswith("hull_"):
        hull_pts += pts
    if ob.get("in_volume", not internal) and not ob.name.startswith("cable_"):  # кабели не считаем
        disp += vol
        mom += vol * c
rep["non_manifold"] = [n for n, p in rep["parts"].items() if not p["manifold"]]


def extent(pts):
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    return lo, hi


lo, hi = extent(hull_pts)
rep["hull_length_mm"] = round((hi[1] - lo[1]) * 1e3, 3)
rep["hull_diameter_y_mm"] = round((hi[0] - lo[0]) * 1e3, 3)
rep["hull_diameter_z_mm"] = round((hi[2] - lo[2]) * 1e3, 3)
lo, hi = extent(all_pts)
rep["overall_ned_mm"] = {"x": round((hi[1] - lo[1]) * 1e3, 1),
                         "y": round((hi[0] - lo[0]) * 1e3, 1),
                         "z": round((hi[2] - lo[2]) * 1e3, 1)}
rep["displaced_volume_l"] = round(disp * 1e3, 4)
rep["cb_model_ned_m"] = ned(mom / disp)
rho = P["rho"]
rep["config_volume_l"] = round((P["mass_dry"] / rho + P["neutral_tank_volume"]) * 1e3, 4)
rep["mass_for_neutral_kg"] = round(disp * rho - P["neutral_tank_volume"] * rho, 3)
rep["config_cb_ned_m"] = P["cb"]
rep["config_cg_ned_m"] = P["cg_dry"]
os.makedirs(os.path.dirname(REPORT), exist_ok=True)
json.dump(rep, open(REPORT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# ---------- экспорт (модификаторы применяются, резаки не выбраны и не попадают) ----------
os.makedirs(os.path.dirname(GLB), exist_ok=True)
for ob in bpy.context.selected_objects:
    ob.select_set(False)
for ob in list(COLL.all_objects):
    ob.select_set(True)
bpy.ops.export_scene.gltf(filepath=GLB, export_format="GLB", use_selection=True,
                          export_extras=True, export_yup=True, export_apply=True)
print(json.dumps({k: v for k, v in rep.items() if k != "parts"}, ensure_ascii=False, indent=1))
