"""Модели лабораторных приборов для зала над бассейном (build_lab_room.py): процедурно, без снимков.

Типы — по виду приборов на снимках скана (осциллографы, генераторы с большой шкалой, стойка усилителей, блоки
питания со стрелочным прибором, приборный ящик с ручкой, приёмник); габариты и места — из скана
(lab_room_items.json, scan_measure.py). Мелкие детали (ручки, тумблеры, разъёмы, надписи) — оценка по снимкам.
Локальные оси прибора: x вправо по лицу, y вглубь (к стене), z вверх; начало — левый нижний угол лица.
"""
import math

import bmesh
import bpy
from mathutils import Matrix, Vector

_mats = {}


def srgb(c):
    return tuple(((v / 255) ** 2.2) for v in c)


def mat(name, col, rough=0.5, metal=0.0, emit=0.0, coat=0.0):
    if name in _mats:
        return _mats[name]
    m = bpy.data.materials.new("DEV_" + name)
    m.use_nodes = True
    m["uv_m"] = 1.0
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*srgb(col), 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["Coat Weight"].default_value = coat
    if emit:
        b.inputs["Emission Color"].default_value = (*srgb(col), 1)
        b.inputs["Emission Strength"].default_value = emit
    _mats[name] = m
    return m


class Dev:
    """Сборщик одного прибора: детали в локальных осях, в конце — один объект."""

    def __init__(self, name):
        self.name = name
        self.bm = bmesh.new()
        self.mats = []

    def _mi(self, m):
        if m not in self.mats:
            self.mats.append(m)
        return self.mats.index(m)

    def box(self, lo, hi, m, bevel=0.0):
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts:
            v.co = Vector([lo[i] + (v.co[i] + 0.5) * (hi[i] - lo[i]) for i in range(3)])
        if bevel > 0:
            bmesh.ops.bevel(bm, geom=bm.edges[:], offset=bevel, segments=2, affect="EDGES", profile=0.5)
        self._merge(bm, m)

    def cyl(self, c, r, depth, m, axis="y", seg=20, r2=None):
        """Цилиндр (конус при r2) с осью axis; c — центр передней (по −y) грани для оси y."""
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r, radius2=r if r2 is None else r2, depth=depth)
        R = {"y": Matrix.Rotation(math.radians(-90), 4, "X"), "z": Matrix.Identity(4), "x": Matrix.Rotation(math.radians(90), 4, "Y")}[axis]
        off = {"y": Vector((0, depth / 2, 0)), "z": Vector((0, 0, depth / 2)), "x": Vector((depth / 2, 0, 0))}[axis]
        bmesh.ops.transform(bm, matrix=Matrix.Translation(Vector(c) + off) @ R, verts=bm.verts)
        self._merge(bm, m)

    def _merge(self, bm, m):
        mi = self._mi(m)
        for f in bm.faces:
            f.material_index = mi
            f.smooth = False
        me = bpy.data.meshes.new("_t")
        bm.to_mesh(me)
        bm.free()
        self.bm.from_mesh(me)
        bpy.data.meshes.remove(me)

    # --- детали лица (на плоскости y = 0, выступают в −y)
    def knob(self, x, z, r=0.012, m=None):
        m = m or mat("bakelite", (22, 21, 20), 0.35)
        self.cyl((x, -0.006, z), r * 1.35, 0.006, m, seg=24)                 # юбка
        self.cyl((x, -0.006 - 0.016, z), r, 0.016, m, seg=24, r2=r * 0.92)
        self.box((x - 0.0012, -0.0225, z + r * 0.3), (x + 0.0012, -0.0215, z + r * 0.95), mat("white_print", (235, 235, 228), 0.6))

    def toggle(self, x, z):
        self.cyl((x, -0.004, z), 0.006, 0.004, mat("chrome", (200, 200, 205), 0.2, 1.0), seg=12)
        self.cyl((x, -0.018, z + 0.004), 0.0018, 0.014, mat("chrome", (200, 200, 205), 0.2, 1.0), seg=8)

    def bnc(self, x, z):
        self.cyl((x, -0.012, z), 0.0065, 0.012, mat("chrome", (200, 200, 205), 0.2, 1.0), seg=14)
        self.cyl((x, -0.013, z), 0.0025, 0.001, mat("bakelite", (22, 21, 20), 0.35), seg=10)

    def lamp(self, x, z, col=(255, 60, 40)):
        self.cyl((x, -0.005, z), 0.004, 0.005, mat(f"led{col}", col, 0.3, emit=1.5), seg=10)

    def label(self, x0, x1, z0, z1, col=(235, 235, 228)):
        self.box((x0, -0.0008, z0), (x1, -0.0002, z1), mat(f"print{col}", col, 0.6))

    def screen(self, x0, x1, z0, z1, glow=(70, 140, 110)):
        """Экран ЭЛТ: рамка, тёмное стекло с лёгким свечением, сетка 8 × 10."""
        self.box((x0 - 0.006, -0.008, z0 - 0.006), (x1 + 0.006, 0.0, z1 + 0.006), mat("bezel", (30, 30, 30), 0.4))
        self.box((x0, -0.0085, z0), (x1, -0.006, z1), mat(f"crt{glow}", glow, 0.08, emit=0.25, coat=1.0))
        gm = mat("grid", (110, 150, 120), 0.3, emit=0.4)
        for i in range(1, 10):
            x = x0 + (x1 - x0) * i / 10
            self.box((x - 0.0004, -0.0088, z0), (x + 0.0004, -0.0086, z1), gm)
        for j in range(1, 8):
            z = z0 + (z1 - z0) * j / 8
            self.box((x0, -0.0088, z - 0.0004), (x1, -0.0086, z + 0.0004), gm)

    def meter(self, x0, x1, z0, z1):
        """Стрелочный прибор: корпус, белая шкала с делениями по дуге, стрелка."""
        self.box((x0 - 0.005, -0.012, z0 - 0.005), (x1 + 0.005, 0.0, z1 + 0.005), mat("bakelite", (22, 21, 20), 0.35))
        self.box((x0, -0.0125, z0), (x1, -0.010, z1), mat("dial", (238, 234, 220), 0.5))
        cx, cz, r = (x0 + x1) / 2, z0 + (z1 - z0) * 0.12, (z1 - z0) * 0.72
        tick = mat("ink", (20, 20, 20), 0.6)
        for i in range(21):
            a = math.radians(140 - 100 * i / 20)
            L = 0.10 if i % 5 == 0 else 0.06
            px, pz = cx + math.cos(a) * r, cz + math.sin(a) * r
            self.box((px - 0.0006, -0.0129, pz - L * r * 0.5), (px + 0.0006, -0.0126, pz + L * r * 0.5), tick)
        a = math.radians(108)
        for k in range(12):
            t = k / 12
            px, pz = cx + math.cos(a) * r * 0.95 * t, cz + math.sin(a) * r * 0.95 * t
            self.box((px - 0.0007, -0.0132, pz - 0.0007), (px + 0.0007, -0.0130, pz + r * 0.08), mat("needle", (190, 30, 20), 0.5))

    def vents(self, x0, x1, y0, y1, z, n, m):
        for i in range(n):
            y = y0 + (y1 - y0) * (i + 0.5) / n
            self.box((x0, y - 0.003, z - 0.0015), (x1, y + 0.003, z + 0.0005), m)

    def feet(self, w, d):
        m = mat("rubber_foot", (25, 25, 25), 0.8)
        for x in (0.03, w - 0.03):
            for y in (0.04, d - 0.04):
                self.box((x - 0.015, y - 0.015, -0.012), (x + 0.015, y + 0.015, 0.0), m)

    def finish(self, coll, corner, rt, inward, zbase):
        me = bpy.data.meshes.new(self.name)
        self.bm.to_mesh(me)
        self.bm.free()
        for m in self.mats:
            me.materials.append(m)
        o = bpy.data.objects.new(self.name, me)
        coll.objects.link(o)
        M = Matrix(((rt.x, inward.x, 0, corner.x), (rt.y, inward.y, 0, corner.y), (0, 0, 1, zbase), (0, 0, 0, 1)))
        o.matrix_world = M
        me.uv_layers.new(name="UVMap")
        return o


# ---------------- типы приборов (w, d, h — габарит по скану)
GREY = (112, 126, 134)        # серо-голубая эмаль приборов 70-80-х (по снимкам)
CREAM = (184, 176, 156)


def case(dv, w, d, h, col, front_col=None, ears=False):
    c = mat(f"case{col}", col, 0.45, coat=0.3)
    dv.box((0.0, 0.0, 0.0), (w, d, h), c, bevel=min(0.008, h * 0.04))
    fc = mat(f"panel{front_col or col}", front_col or col, 0.5)
    dv.box((0.006, -0.002, 0.006), (w - 0.006, 0.004, h - 0.006), fc)
    if ears:
        for x0 in (-0.02, w):
            dv.box((x0, -0.004, 0.0), (x0 + 0.02, 0.002, h), mat("chrome", (200, 200, 205), 0.2, 1.0))
    dv.feet(w, d)


def handles(dv, w, h):
    """Ручки для переноски на лицевой панели по бокам (хром), как у приборов 70-80-х."""
    m = mat("chrome", (200, 200, 205), 0.2, 1.0)
    for x in (0.012, w - 0.012):
        dv.box((x - 0.005, -0.03, h * 0.15), (x + 0.005, -0.024, h * 0.85), m)
        for z in (h * 0.15, h * 0.85 - 0.01):
            dv.box((x - 0.005, -0.03, z), (x + 0.005, 0.0, z + 0.01), m)


def oscilloscope(dv, w, d, h):
    case(dv, w, d, h, GREY, (128, 140, 146))
    handles(dv, w, h)
    sw, sh = min(w * 0.42, h * 0.75 * 1.25), min(h * 0.62, w * 0.34)
    dv.screen(0.03, 0.03 + sw, h - 0.03 - sh, h - 0.03, (28, 55, 42))
    x0 = 0.03 + sw + 0.03
    cols = max(2, int((w - x0 - 0.02) / 0.045))
    for i in range(cols):
        for j, zz in enumerate((h * 0.75, h * 0.5, h * 0.25)):
            dv.knob(x0 + i * (w - x0 - 0.03) / max(cols - 1, 1), zz, 0.010 if j else 0.013)
    for k in range(3):
        dv.bnc(0.04 + k * 0.05, 0.035)
    dv.toggle(0.03 + sw - 0.02, 0.035)
    dv.lamp(0.03 + sw - 0.05, 0.035)
    dv.label(0.03, 0.03 + sw * 0.5, h - 0.022, h - 0.014)
    dv.vents(0.03, w - 0.03, 0.05, d - 0.05, h + 0.0005, 10, mat("slot", (25, 25, 25), 0.8))


def generator(dv, w, d, h):
    case(dv, w, d, h, CREAM, (172, 166, 148))
    handles(dv, w, h)
    r = min(h, w) * 0.28
    cx, cz = w * 0.5, h * 0.42
    dv.cyl((cx, -0.004, cz), r * 1.1, 0.004, mat("bezel", (30, 30, 30), 0.4), seg=48)
    dv.cyl((cx, -0.008, cz), r, 0.004, mat("dial", (238, 234, 220), 0.5), seg=48)
    tick = mat("ink", (20, 20, 20), 0.6)
    for i in range(36):
        a = 2 * math.pi * i / 36
        L = r * (0.16 if i % 3 == 0 else 0.08)
        px, pz = cx + math.cos(a) * (r - L), cz + math.sin(a) * (r - L)
        dv.box((px - 0.0007, -0.0085, pz - 0.0007), (px + 0.0007, -0.0083, pz + 0.0007 + L * 0.6), tick)
    dv.cyl((cx, -0.026, cz), r * 0.35, 0.018, mat("bakelite", (22, 21, 20), 0.35), seg=32)
    for k, x in enumerate((0.05, 0.10, w - 0.10, w - 0.05)):
        dv.knob(x, h * 0.72, 0.012)
        dv.knob(x, h * 0.2, 0.010)
    dv.box((w * 0.3, -0.006, h * 0.80), (w * 0.7, 0.0, h * 0.92), mat("window_dark", (40, 30, 25), 0.2, coat=1.0))
    for i in range(6):
        dv.lamp(w * 0.32 + i * w * 0.07, h * 0.86, (255, 140, 40))
    dv.bnc(w - 0.04, 0.03)
    dv.toggle(0.04, 0.03)
    dv.label(0.03, 0.12, h - 0.02, h - 0.012)


def amplifier(dv, w, d, h, units=2):
    uh = h / units
    for u in range(units):
        z0 = u * uh
        c = mat("amp_black", (24, 24, 25), 0.35, coat=0.2)
        dv.box((0.0, 0.0, z0 + 0.002), (w, d, z0 + uh - 0.002), c, bevel=0.003)
        dv.box((0.02, -0.003, z0 + 0.008), (w - 0.02, 0.0, z0 + uh - 0.008), mat("amp_panel", (34, 34, 36), 0.3, 0.6))
        for x0 in (-0.022, w):
            dv.box((x0, -0.004, z0 + 0.004), (x0 + 0.022, 0.002, z0 + uh - 0.004), mat("amp_panel", (34, 34, 36), 0.3, 0.6))
        for k in range(2):
            mx = w * 0.30 + k * w * 0.22
            dv.meter(mx, mx + w * 0.16, z0 + uh * 0.35, z0 + uh * 0.80)
        for x in (w * 0.08, w * 0.16):
            dv.knob(x, z0 + uh * 0.5, 0.010, mat("alu", (180, 180, 182), 0.3, 1.0))
        dv.box((w * 0.78, -0.006, z0 + uh * 0.3), (w * 0.92, 0.0, z0 + uh * 0.7), mat("alu", (180, 180, 182), 0.3, 1.0))
        dv.lamp(w * 0.74, z0 + uh * 0.5, (60, 160, 255))
        dv.label(w * 0.30, w * 0.70, z0 + uh * 0.86, z0 + uh * 0.92)
        for i in range(12):
            x = w * 0.08 + i * w * 0.07
            dv.box((x, 0.02, z0 + uh - 0.0015), (x + w * 0.04, d - 0.04, z0 + uh - 0.001), mat("slot", (12, 12, 12), 0.8))


def power_supply(dv, w, d, h):
    case(dv, w, d, h, GREY, (126, 136, 140))
    handles(dv, w, h)
    dv.meter(w * 0.12, w * 0.62, h * 0.45, h * 0.85)
    dv.knob(w * 0.80, h * 0.70, 0.016)
    dv.knob(w * 0.80, h * 0.40, 0.012)
    for k in range(2):
        dv.cyl((w * (0.2 + 0.18 * k), -0.012, h * 0.18), 0.008, 0.012, mat(f"term{k}", ((200, 30, 20), (20, 20, 20))[k], 0.4), seg=14)
    dv.toggle(w * 0.80, h * 0.15)
    dv.lamp(w * 0.66, h * 0.15)
    dv.label(w * 0.12, w * 0.5, h * 0.9, h * 0.94)
    dv.vents(w * 0.1, w * 0.9, 0.05, d - 0.05, h + 0.0005, 8, mat("slot", (25, 25, 25), 0.8))


def instrument_case(dv, w, d, h):
    """Приборный ящик (переносной, металл) с ручкой сверху и решётками по бокам."""
    c = mat("case_blue", (95, 120, 140), 0.45, coat=0.3)
    dv.box((0.0, 0.0, 0.0), (w, d, h), c, bevel=0.012)
    dv.box((0.02, -0.003, 0.02), (w - 0.02, 0.0, h - 0.02), mat("case_blue_lid", (105, 130, 150), 0.45))
    for i in range(6):
        z = h * 0.15 + i * h * 0.06
        dv.box((w * 0.25, -0.006, z), (w * 0.75, -0.002, z + h * 0.025), mat("slot", (25, 25, 25), 0.8))
    for x in (w * 0.08, w * 0.92):
        dv.box((x - 0.012, -0.008, h * 0.72), (x + 0.012, 0.0, h * 0.8), mat("chrome", (200, 200, 205), 0.2, 1.0))
    hm = mat("handle", (30, 30, 30), 0.5)
    dv.box((w * 0.3, d * 0.4, h), (w * 0.33, d * 0.6, h + 0.04), hm)
    dv.box((w * 0.67, d * 0.4, h), (w * 0.70, d * 0.6, h + 0.04), hm)
    dv.box((w * 0.3, d * 0.45, h + 0.035), (w * 0.70, d * 0.55, h + 0.05), hm)
    dv.feet(w, d)


def receiver(dv, w, d, h):
    case(dv, w, d, h, (60, 62, 64), (45, 46, 48))
    dv.box((w * 0.06, -0.006, h * 0.55), (w * 0.94, 0.0, h * 0.88), mat("scale_glass", (210, 200, 160), 0.2, emit=0.2, coat=1.0))
    tick = mat("ink", (20, 20, 20), 0.6)
    for i in range(30):
        x = w * 0.08 + i * w * 0.84 / 29
        dv.box((x - 0.0006, -0.0065, h * 0.62), (x + 0.0006, -0.0062, h * (0.70 if i % 5 else 0.76)), tick)
    dv.box((w * 0.45, -0.007, h * 0.58), (w * 0.455, -0.0066, h * 0.85), mat("needle", (190, 30, 20), 0.5))
    for k, x in enumerate((0.15, 0.35, 0.65, 0.85)):
        dv.knob(w * x, h * 0.28, 0.016 if k in (0, 3) else 0.011, mat("alu", (180, 180, 182), 0.3, 1.0))
    dv.lamp(w * 0.5, h * 0.28, (120, 255, 120))


TYPES = {"osc": oscilloscope, "gen": generator, "amp": amplifier, "psu": power_supply, "case": instrument_case, "rx": receiver}


def build(coll, name, kind, o, dvv, nv, a0, a1, b0, b1, z0, z1):
    """Прибор kind в габарите стола (o, dv, nv; a — вдоль, b — от стены в зал, z — высота)."""
    dvv, nv = Vector((*dvv, 0)).normalized(), Vector((*nv, 0)).normalized()
    rt = Vector((-nv.y, nv.x, 0))
    a_left = a0 if rt.dot(dvv) > 0 else a1
    corner = Vector((*o, 0)) + dvv * a_left + nv * b1
    w, d, h = abs(a1 - a0), abs(b1 - b0), z1 - z0
    dv = Dev(name)
    TYPES[kind](dv, w, d, h)
    return dv.finish(coll, corner, rt, -nv, z0)


# ---------------- шкафы (размеры по скану, устройство — оценка по снимкам)
WOOD = (120, 72, 40)          # полированный шпон (по снимкам — рыже-коричневый)


def _glass():
    if "glass" in _mats:
        return _mats["glass"]
    m = bpy.data.materials.new("DEV_glass")
    m.use_nodes = True
    m["uv_m"] = 1.0
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (0.9, 0.95, 0.95, 1)
    b.inputs["Transmission Weight"].default_value = 1.0
    b.inputs["Roughness"].default_value = 0.02
    b.inputs["IOR"].default_value = 1.5
    _mats["glass"] = m
    return m


def _doors(dv, x0, x1, z0, z1, m, n=2, knob=True):
    """Филёнчатые двери на лице (выступают на 1 см), щель 4 мм, ручки."""
    wd = (x1 - x0) / n
    for i in range(n):
        a, b = x0 + i * wd + 0.002, x0 + (i + 1) * wd - 0.002
        dv.box((a, -0.012, z0), (b, 0.0, z1), m, bevel=0.002)
        dv.box((a + 0.03, -0.016, z0 + 0.03), (b - 0.03, -0.012, z1 - 0.03), m)
        if knob:
            xk = b - 0.03 if i % 2 == 0 else a + 0.03
            dv.box((xk - 0.006, -0.03, (z0 + z1) / 2 - 0.03), (xk + 0.006, -0.016, (z0 + z1) / 2 + 0.03),
                   mat("brass", (190, 150, 70), 0.3, 1.0))


def _shelf_items(dv, x0, x1, z, depth, rnd):
    x = x0 + 0.01
    while x < x1 - 0.04:
        w = rnd.uniform(0.03, 0.12)
        h = rnd.uniform(0.04, 0.2)
        c = rnd.choice([(150, 150, 155), (60, 60, 65), (180, 140, 70), (120, 40, 30), (40, 80, 120), (200, 200, 195)])
        if rnd.random() < 0.4:
            dv.cyl((x + w / 2, 0.05, z + h / 2), w / 2, depth * 0.5, mat(f"part{c}", c, 0.4, 0.5 if c[0] > 140 else 0.0), seg=14)
        else:
            dv.box((x, 0.04, z), (min(x + w, x1 - 0.01), 0.04 + depth * rnd.uniform(0.3, 0.8), z + h), mat(f"part{c}", c, 0.5))
        x += w + rnd.uniform(0.005, 0.03)


def glass_cabinet(dv, w, d, h):
    import random
    rnd = random.Random(4)
    wood = mat("wood", WOOD, 0.35, coat=0.5)
    dv.box((0, 0, 0), (w, d, 0.72), wood, bevel=0.004)
    _doors(dv, 0.01, w - 0.01, 0.04, 0.70, wood)
    st = mat("steel_frame", (70, 72, 74), 0.4, 0.8)
    for x in (0.0, w - 0.025):
        dv.box((x, 0.0, 0.72), (x + 0.025, d, h), st)
    dv.box((0, 0, h - 0.03), (w, d, h), st)
    dv.box((0.02, d - 0.01, 0.72), (w - 0.02, d, h), mat("cab_back", (200, 200, 195), 0.7))
    for k in range(4):
        z = 0.74 + k * (h - 0.78) / 4
        dv.box((0.025, 0.0, z), (w - 0.025, d - 0.01, z + 0.01), _glass())
        _shelf_items(dv, 0.03, w - 0.03, z + 0.01, d - 0.08, rnd)
    for i in range(2):
        a, b = 0.025 + i * (w - 0.05) / 2, 0.025 + (i + 1) * (w - 0.05) / 2
        dv.box((a, -0.012, 0.73), (b, -0.006, h - 0.03), _glass())
        dv.box((a, -0.014, 0.73), (a + 0.012, -0.006, h - 0.03), st)
        dv.box((b - 0.012, -0.014, 0.73), (b, -0.006, h - 0.03), st)


def metal_cabinet(dv, w, d, h):
    g = mat("cab_grey", (96, 102, 98), 0.45, 0.4, coat=0.2)
    dv.box((0, 0, 0), (w, d, h), g, bevel=0.004)
    _doors(dv, 0.005, w - 0.005, 0.06, h - 0.02, g, 2, knob=False)
    for x in (w / 2 - 0.03, w / 2 + 0.03):
        dv.box((x - 0.006, -0.035, h * 0.5 - 0.06), (x + 0.006, -0.012, h * 0.5 + 0.06), mat("chrome", (200, 200, 205), 0.2, 1.0))
    dv.cyl((w / 2 + 0.07, -0.016, h * 0.56), 0.008, 0.006, mat("chrome", (200, 200, 205), 0.2, 1.0), seg=12)
    for i in range(5):
        z = h - 0.18 + i * 0.022
        for x0 in (0.06, w / 2 + 0.06):
            dv.box((x0, -0.017, z), (x0 + w * 0.3, -0.015, z + 0.008), mat("slot", (25, 25, 25), 0.8))
    dv.box((0, -0.002, 0), (w, 0.02, 0.06), mat("plinth", (40, 40, 40), 0.7))


def bookcase(dv, w, d, h):
    import random
    rnd = random.Random(9)
    wood = mat("wood", WOOD, 0.35, coat=0.5)
    dv.box((0, 0, 0), (w, d, h), wood, bevel=0.004)
    dv.box((0.03, -0.001, 0.80), (w - 0.03, d - 0.02, h - 0.06), mat("cab_inside", (70, 45, 28), 0.6))
    _doors(dv, 0.01, w - 0.01, 0.06, 0.78, wood)
    for k in range(3):
        z = 0.82 + k * (h - 0.9) / 3
        dv.box((0.03, 0.0, z - 0.012), (w - 0.03, d - 0.02, z), wood)
        x = 0.04
        while x < w - 0.06:
            bw = rnd.uniform(0.018, 0.045)
            bh = rnd.uniform(0.16, (h - 0.9) / 3 - 0.03)
            c = rnd.choice([(120, 30, 30), (30, 50, 90), (40, 80, 50), (180, 160, 120), (60, 40, 30), (150, 140, 120), (200, 190, 160)])
            tilt = 0.0
            dv.box((x, 0.03, z), (x + bw, d - 0.04, z + bh), mat(f"book{c}", c, 0.7))
            x += bw + rnd.uniform(0.0, 0.006)
    for i in range(2):
        a, b = 0.03 + i * (w - 0.06) / 2, 0.03 + (i + 1) * (w - 0.06) / 2
        dv.box((a, -0.014, 0.80), (b, -0.008, h - 0.06), _glass())
        for (p0, p1) in (((a, 0.80), (a + 0.03, h - 0.06)), ((b - 0.03, 0.80), (b, h - 0.06)),
                         ((a, 0.80), (b, 0.83)), ((a, h - 0.09), (b, h - 0.06))):
            dv.box((p0[0], -0.018, p0[1]), (p1[0], -0.006, p1[1]), wood)


def wardrobe(dv, w, d, h):
    wood = mat("wood", WOOD, 0.35, coat=0.5)
    dv.box((0, 0, 0), (w, d, h), wood, bevel=0.004)
    _doors(dv, 0.01, w - 0.01, 0.08, h - 0.05, wood)
    dv.box((-0.015, -0.02, h - 0.04), (w + 0.015, d, h), wood)
    dv.box((0, -0.004, 0), (w, d, 0.07), mat("plinth", (40, 40, 40), 0.7))


TYPES.update({"glass_cabinet": glass_cabinet, "metal_cabinet": metal_cabinet, "bookcase": bookcase, "wardrobe": wardrobe})


def build_at(coll, name, kind, corner, rt, inward, z0, w, d, h):
    """Модель kind по левому нижнему углу лица corner, оси rt (вправо) и inward (вглубь)."""
    dv = Dev(name)
    TYPES[kind](dv, w, d, h)
    return dv.finish(coll, Vector((corner.x, corner.y, 0)), Vector(rt), Vector(inward), z0)
