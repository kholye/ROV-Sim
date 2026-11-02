class_name Fauna
extends Node3D
## Подвижная живность у затонувшего судна (оценка: северное мелководье, Белое, Баренцево, Северное море
## на 5-10 м; на физику аппарата не влияет, столкновений нет, правила осмотра не меняет). Судно — искусственный
## риф: рыба держится у корпуса плотнее, чем над голым илом.
##  - стая тресочки (Trisopterus luscus, 15-25 см, 110 шт.) обходит корпус вплотную в 0,5-2,2 м над илом;
##  - сайда (Pollachius virens, 40-60 см, 18 шт.) кружит над судном в 3-4 м от дна;
##  - стая шпрота (Sprattus sprattus, 9-13 см, 48 шт.) — шире, в 7 м от середины судна;
##  - треска (Gadus morhua, 35-55 см) и губаны (Labrus bergylta, 25-40 см) держатся у своих мест у корпуса
##    (пустые объекты Home_cod_*, Home_wrasse_* из Blender), бродят и зависают;
##  - камбала (Platichthys flesus, 22-32 см) лежит на иле (Home_flounder_*), срывается, если аппарат ближе 1,2 м;
##  - крабы (Carcinus maenas, панцирь 6-8 см) ходят боком у дна (Home_crab_*).
## Рыбы уходят от аппарата: реакция на подводные аппараты в пределах 1-3 м (Stoner и др. 2008),
## дистанции ниже — оценка. Частота хвоста по Bainbridge 1958: U/L = 0,75·f − 1, т. е. f = (U/L + 1)/0,75 Гц, размах 0,2 L
## (соотношение выведено для f > 5 Гц, на малых скоростях — продолжение, оценка).
## Новая цель проверяется лучом (путь свободен, до дна не меньше CLEAR) по слою 1: судно, дно, предметы.

const FISH_SHADER := preload("res://shaders/underwater_fish.gdshader")
const COD_FLEE := 1.8
const FLOUNDER_FLEE := 1.2
const CRAB_FLEE := 0.8
const CLEAR := 0.35            # просвет до дна у новой цели трески, м
const HALF_L := 5.1            # полудлина и полуширина корпуса в плане (как в build_wreck_site.py)
const HALF_B := 2.5


class Animal:
	var p := Vector3.ZERO
	var v := Vector3.ZERO
	var dir := Vector3.FORWARD
	var size := 0.1
	var phase := 0.0
	var amp := 0.0
	var bend := 0.0
	var home := Vector3.ZERO
	var target := Vector3.ZERO
	var slot := Vector3.ZERO
	var speed := 0.1
	var wait := 0.0
	var state := 0              # 0 — бродит / лежит, 1 — уходит от аппарата, 2 — оседает (камбала)
	var ground_y := 0.0
	var side := 1.0             # краб: в какую сторону идёт боком


var rov: Node3D
var center := Vector3.ZERO
var rng := RandomNumberGenerator.new()
var schools := {}               # вид -> материал стаи (движение — в шейдере)
var loiter := {}                # вид -> Array[Animal] (треска, губаны)
var flounders: Array[Animal] = []
var crabs: Array[Animal] = []
var _mm := {}                   # вид -> MultiMesh
var _t := 0.0
var _ship_c := Vector3.ZERO     # середина судна и оси к носу и к правому борту (по Home ShipStern / ShipBow)
var _ship_f := Vector3.FORWARD
var _ship_r := Vector3.RIGHT


## site — сцена места (wreck_site.glb) с пустыми Home_*; center — середина судна на уровне дна.
func setup(rov_: Node3D, site: Node, center_: Vector3) -> void:
	rov = rov_
	center = center_
	rng.seed = 1904
	name = "Fauna"
	var cods: Array[Animal] = []
	var wrasses: Array[Animal] = []
	for n in site.find_children("Home_*", "", true, false):
		var hp := (n as Node3D).global_position
		var a := Animal.new()
		a.home = hp
		a.p = hp
		a.target = hp
		a.wait = rng.randf_range(0.0, 4.0)
		a.dir = Vector3(rng.randf_range(-1, 1), 0, rng.randf_range(-1, 1)).normalized()
		a.phase = rng.randf() * TAU
		var nm := String(n.name)
		if nm.begins_with("Home_cod"):
			a.size = rng.randf_range(0.35, 0.55)
			cods.append(a)
		elif nm.begins_with("Home_wrasse"):
			a.size = rng.randf_range(0.25, 0.4)
			wrasses.append(a)
		elif nm.begins_with("Home_flounder"):
			a.size = rng.randf_range(0.22, 0.32)
			a.ground_y = hp.y
			a.p.y = hp.y + 0.012
			flounders.append(a)
		else:
			a.size = rng.randf_range(0.06, 0.08)
			a.ground_y = hp.y
			a.side = 1.0 if rng.randf() < 0.5 else -1.0
			crabs.append(a)
	loiter = {"cod": cods, "wrasse": wrasses}
	var stern := (site.find_child("ShipStern", true, false) as Node3D).global_position
	var bow := (site.find_child("ShipBow", true, false) as Node3D).global_position
	_ship_c = (stern + bow) * 0.5
	_ship_f = Vector3(bow.x - stern.x, 0, bow.z - stern.z).normalized()
	_ship_r = _ship_f.cross(Vector3.UP)
	# стаи — на видеокарте (shaders/underwater_fish.gdshader, school): эллипс, высота, скорость, уход от аппарата
	var up_c := center
	_gpu_school("sprat", 48, Vector2(0.09, 0.13), Vector3(2.5, 0.35, 0.9), _fish_mesh(0.18, 0.1, Color(0.03, 0.055, 0.065),
			Color(0.42, 0.44, 0.47), 0.05), {"center": up_c, "a1": Vector3.RIGHT, "a2": Vector3.BACK, "radii": Vector2(7.5, 6.0),
			"omega": 0.02, "h0": center.y + 3.0, "flee": 2.5, "min_y": center.y + 1.2})
	_gpu_school("saithe", 18, Vector2(0.4, 0.6), Vector3(1.6, 0.45, 1.0), _fish_mesh(0.19, 0.12, Color(0.035, 0.05, 0.045),
			Color(0.36, 0.37, 0.36), 0.08), {"center": _ship_c, "a1": _ship_f, "a2": _ship_r, "radii": Vector2(3.5, 2.8),
			"omega": -0.04, "h0": center.y + 3.6, "flee": 2.5, "min_y": center.y + 2.0})
	_gpu_school("bib", 110, Vector2(0.15, 0.25), Vector3(2.2, 0.5, 0.6), _fish_mesh(0.3, 0.13, Color(0.22, 0.12, 0.05),
			Color(0.42, 0.36, 0.28), 0.1, false, true), {"center": _ship_c, "a1": _ship_f, "a2": _ship_r,
			"radii": Vector2(HALF_L + 1.8, HALF_B + 1.6), "omega": 0.024, "h0": center.y + 1.3, "flee": 1.8, "min_y": center.y + 0.45})
	_group("cod", _fish_mesh(0.21, 0.15, Color(0.10, 0.09, 0.045), Color(0.38, 0.37, 0.31), 0.35), cods.size(), Vector3.RIGHT)
	_group("wrasse", _fish_mesh(0.28, 0.16, Color(0.07, 0.09, 0.04), Color(0.25, 0.2, 0.1), 0.5), wrasses.size(), Vector3.RIGHT)
	_group("flounder", _fish_mesh(0.055, 0.5, Color(0.075, 0.062, 0.04), Color(0.45, 0.45, 0.42), 0.45, true),
			flounders.size(), Vector3.UP)
	_group("crab", _crab_mesh(Color(0.10, 0.095, 0.035)), crabs.size(), Vector3.ZERO)
	_draw()


func _group(kind: String, mesh: ArrayMesh, n: int, wave_axis: Vector3) -> void:
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.use_custom_data = true
	mm.mesh = mesh
	mm.instance_count = n
	var mi := MultiMeshInstance3D.new()
	mi.name = kind
	mi.multimesh = mm
	var m := ShaderMaterial.new()
	m.shader = FISH_SHADER
	m.set_shader_parameter("wave_axis", wave_axis)
	mi.material_override = Underwater.register(m)
	mi.custom_aabb = AABB(Vector3(-30, -15, -30), Vector3(60, 20, 60))   # рыбы ходят по всему месту
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(mi)
	_mm[kind] = mm


## Стая на видеокарте: экземпляры с единичным преобразованием, данные экземпляра = место (slot) и длина;
## параметры пути — в материале (prm: center, a1, a2, radii, omega, h0, flee, min_y). Частота хвоста по
## Bainbridge при скорости стаи U = |ω|·R.
func _gpu_school(kind: String, n: int, size: Vector2, spread: Vector3, mesh: ArrayMesh, prm: Dictionary) -> void:
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.use_custom_data = true
	mm.mesh = mesh
	mm.instance_count = n
	var mean_len := 0.5 * (size.x + size.y)
	for i in n:
		mm.set_instance_transform(i, Transform3D.IDENTITY)
		mm.set_instance_custom_data(i, Color(rng.randfn(0, spread.x), rng.randfn(0, spread.y), rng.randfn(0, spread.z),
				rng.randf_range(size.x, size.y)))
	var m := ShaderMaterial.new()
	m.shader = FISH_SHADER
	m.set_shader_parameter("wave_axis", Vector3.RIGHT)
	m.set_shader_parameter("school", true)
	for k in prm:
		m.set_shader_parameter("s_" + k, prm[k])
	var radii: Vector2 = prm["radii"]
	var u := absf(float(prm["omega"])) * 0.5 * (radii.x + radii.y)
	m.set_shader_parameter("s_freq", (u / mean_len + 1.0) / 0.75)
	var mi := MultiMeshInstance3D.new()
	mi.name = kind
	mi.multimesh = mm
	mi.material_override = Underwater.register(m)
	mi.custom_aabb = AABB(Vector3(-30, -15, -30), Vector3(60, 20, 60))
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(mi)
	schools[kind] = m


func _ray(a: Vector3, b: Vector3) -> Dictionary:
	var q := PhysicsRayQueryParameters3D.create(a, b, 1)
	return get_world_3d().direct_space_state.intersect_ray(q)


## Высота дна (или предмета) под точкой; если луч ничего не нашёл — запасное значение.
func _ground(p: Vector3, fallback: float) -> float:
	var hit := _ray(p + Vector3.UP * 0.6, p + Vector3.DOWN * 2.0)
	return (hit["position"] as Vector3).y if not hit.is_empty() else fallback


## Новая цель у точки around в пределах r (по вертикали rv): путь от p свободен, до дна не меньше clear.
func _pick(a: Animal, around: Vector3, r: float, rv: float, clear: float) -> bool:
	for _i in 8:
		var c := around + Vector3(rng.randf_range(-r, r), rng.randf_range(-rv, rv), rng.randf_range(-r, r))
		if _ray(a.p, c).is_empty() and _ray(c, c + Vector3.DOWN * clear).is_empty():
			a.target = c
			return true
	return false


## Точка на дне в 2,5-4 м от p в сторону away (камбала, краб): путь над дном свободен.
func _pick_ground(a: Animal, away: Vector3, dmin: float, dmax: float, lift: float) -> bool:
	for k in 8:
		var ang := rng.randf_range(-0.6, 0.6) * (1.0 + k * 0.3)
		var d := away.rotated(Vector3.UP, ang) * rng.randf_range(dmin, dmax)
		var from := a.p + Vector3.UP * lift
		var to := from + d
		if _ray(from, to).is_empty():
			var gy := _ground(to, a.ground_y)
			if absf(gy - a.ground_y) < 0.4:
				a.target = Vector3(to.x, gy, to.z)
				return true
	return false


func _physics_process(delta: float) -> void:
	if rov == null:
		return
	_t += delta
	var rp := rov.global_position
	for a in loiter["cod"]:
		_loiter(a, delta, rp, 1.5, 0.15)
	for a in loiter["wrasse"]:
		_loiter(a, delta, rp, 0.8, 0.1)
	for a in flounders:
		_flounder(a, delta, rp)
	for a in crabs:
		_crab(a, delta, rp)
	_draw()


## Треска, губаны: бродят около своего места (в пределах roam м), зависают, отходят от аппарата.
func _loiter(a: Animal, delta: float, rp: Vector3, roam: float, speed: float) -> void:
	var d := a.p - rp
	if d.length() < COD_FLEE and a.state == 0:
		var away := Vector3(d.x, 0, d.z).normalized()
		if _pick(a, a.p + away * 2.5, 0.8, 0.2, CLEAR):
			a.state = 1
			a.wait = 0.0
	var want := Vector3.ZERO
	if a.wait > 0.0:
		a.wait -= delta                      # зависает, работая плавниками
	elif a.p.distance_to(a.target) < 0.2:
		a.state = 0
		a.wait = rng.randf_range(2.0, 8.0)
		_pick(a, a.home, roam, 0.3, CLEAR)
	else:
		var spd := 0.7 if a.state == 1 else speed
		want = (a.target - a.p).normalized() * minf(spd, a.p.distance_to(a.target) * 1.5)
	_swim(a, want, delta, 1.2 if a.state == 0 else 3.0, a.dir)


func _process(_dt: float) -> void:
	if rov:
		for kind in schools:
			(schools[kind] as ShaderMaterial).set_shader_parameter("rov_pos", rov.global_position)


func _flounder(a: Animal, delta: float, rp: Vector3) -> void:
	var d := a.p - rp
	match a.state:
		0:                                   # лежит на иле
			a.v = Vector3.ZERO
			a.amp = 0.02
			a.phase += delta * 2.0
			if d.length() < FLOUNDER_FLEE and _pick_ground(a, Vector3(d.x, 0, d.z).normalized(), 2.5, 4.0, 0.2):
				a.state = 1
		1:                                   # уходит низко над дном
			var flat := Vector3(a.target.x - a.p.x, 0, a.target.z - a.p.z)
			var gy := _ground(a.p, a.ground_y)
			a.ground_y = gy
			var want := flat.normalized() * 0.45
			want.y = (gy + 0.2 - a.p.y) * 3.0
			_swim(a, want, delta, 4.0, a.dir)
			a.dir = Vector3(a.dir.x, 0, a.dir.z).normalized()
			if flat.length() < 0.15:
				a.state = 2
		2:                                   # оседает за 1 с
			a.v = Vector3.ZERO
			a.ground_y = _ground(a.p, a.ground_y)
			a.p.y = move_toward(a.p.y, a.ground_y + 0.012, 0.2 * delta)
			a.amp = 0.08
			a.phase += delta * 6.0
			if a.p.y <= a.ground_y + 0.0125:
				a.state = 0
	a.bend = 0.0


func _crab(a: Animal, delta: float, rp: Vector3) -> void:
	var d := a.p - rp
	if d.length() < CRAB_FLEE and a.state == 0:
		if _pick_ground(a, Vector3(d.x, 0, d.z).normalized(), 0.5, 1.0, 0.05):
			a.state = 1
			a.wait = 0.0
	if a.wait > 0.0:
		a.wait -= delta
		return
	var flat := Vector3(a.target.x - a.p.x, 0, a.target.z - a.p.z)
	if flat.length() < 0.03:
		a.state = 0
		a.wait = rng.randf_range(3.0, 12.0)
		var back := Vector3(a.home.x - a.p.x, 0, a.home.z - a.p.z)
		if back.length() < 0.1:
			back = Vector3.FORWARD
		if not _pick_ground(a, back.normalized().rotated(Vector3.UP, rng.randf_range(-1.5, 1.5)), 0.3, 1.2, 0.05):
			a.wait = 2.0
		return
	var mv := flat.normalized()
	a.p += mv * (0.1 if a.state == 1 else 0.04) * delta
	a.ground_y = _ground(a.p, a.ground_y)
	a.p.y = a.ground_y
	var fwd := Vector3.UP.cross(mv) * a.side   # идёт боком: панцирь поперёк пути
	a.dir = a.dir.lerp(fwd, minf(1.0, delta * 2.0)).normalized()


## Общий ход рыбы: скорость к want, поворот носа по скорости (или к rest_dir, если почти стоит),
## частота хвоста по Bainbridge, изгиб тела на повороте.
func _swim(a: Animal, want: Vector3, delta: float, agility: float, rest_dir: Vector3) -> void:
	a.v = a.v.lerp(want, 1.0 - exp(-delta * agility))
	a.p += a.v * delta
	var u := a.v.length()
	var look := a.v / u if u > 0.04 else rest_dir
	look.y = clampf(look.y, -0.45, 0.45)
	look = look.normalized()
	var old := a.dir
	a.dir = a.dir.lerp(look, minf(1.0, delta * agility * 1.2)).normalized()
	var turn := old.cross(a.dir).y / maxf(delta, 1e-4)        # рад/с, > 0 — влево
	a.bend = lerpf(a.bend, clampf(-turn * 0.06, -0.12, 0.12), minf(1.0, delta * 4.0))
	var f := (u / a.size + 1.0) / 0.75
	a.phase = fmod(a.phase + TAU * f * delta, TAU * 100.0)
	a.amp = lerpf(0.06, 0.2, clampf(u / a.size, 0.0, 1.0))


func _draw() -> void:
	for kind in loiter:
		_put(kind, loiter[kind])
	_put("flounder", flounders)
	_put("crab", crabs)


## Все экземпляры вида одним буфером (12 чисел преобразования по строкам + 4 данных экземпляра):
## в разы быстрее, чем по вызову set_instance_transform на рыбу.
func _put(kind: String, list: Array[Animal]) -> void:
	var mm: MultiMesh = _mm[kind]
	var buf := PackedFloat32Array()
	buf.resize(list.size() * 16)
	var lift := 0.05 if kind == "crab" else 0.0
	for i in list.size():
		var a := list[i]
		var b := Basis.looking_at(a.dir, Vector3.UP).scaled(Vector3.ONE * a.size)
		var o := a.p + Vector3.UP * (lift * a.size)
		var k := i * 16
		buf[k] = b.x.x
		buf[k + 1] = b.y.x
		buf[k + 2] = b.z.x
		buf[k + 3] = o.x
		buf[k + 4] = b.x.y
		buf[k + 5] = b.y.y
		buf[k + 6] = b.z.y
		buf[k + 7] = o.y
		buf[k + 8] = b.x.z
		buf[k + 9] = b.y.z
		buf[k + 10] = b.z.z
		buf[k + 11] = o.z
		buf[k + 12] = a.phase
		buf[k + 13] = a.amp
		buf[k + 14] = a.bend
	mm.buffer = buf


static func _hash(k: int) -> float:
	return fposmod(sin(k * 12.9898) * 43758.5453, 1.0)


## Рыба длиной 1 (нос −Z): 7 колец по профилю тела, хвостовой и спинной плавники, глаза.
## h, w — высота и толщина в долях длины; mottle — пятнистость; flat — камбала (хвост горизонтально);
## bars — тёмные поперечные полосы.
func _fish_mesh(h: float, w: float, back: Color, belly: Color, mottle: float, flat := false, bars := false) -> ArrayMesh:
	var T := [0.0, 0.1, 0.25, 0.45, 0.65, 0.85, 1.0]
	var F := [0.15, 0.65, 0.92, 1.0, 0.8, 0.45, 0.22] if not flat else [0.2, 0.7, 0.95, 1.0, 0.9, 0.55, 0.2]
	var seg := 8
	var vs := PackedVector3Array()
	var ns := PackedVector3Array()
	var cs := PackedColorArray()
	var ix := PackedInt32Array()
	for r in T.size():
		var z := -0.5 + 0.8 * float(T[r])
		for i in seg:
			var q := TAU * i / seg
			vs.append(Vector3(0.5 * w * F[r] * cos(q), 0.5 * h * F[r] * sin(q), z))
			ns.append(Vector3(h * cos(q), w * sin(q), 0.0).normalized())
			var col := belly.lerp(back, smoothstep(-0.35, 0.35, sin(q)))
			col = col * (1.0 - mottle + 2.0 * mottle * _hash(r * 31 + i * 7))
			if bars and r in [2, 4] and sin(q) > -0.3:
				col = col * 0.45                                   # тёмные поперечные полосы (тресочка)
			if r == 1 and (i == 1 or i == 3):
				col = Color(0.01, 0.01, 0.01)                      # глаза
			cs.append(col)
	for r in T.size() - 1:
		for i in seg:
			var j := (i + 1) % seg
			ix.append_array([r * seg + i, (r + 1) * seg + i, (r + 1) * seg + j, r * seg + i, (r + 1) * seg + j, r * seg + j])
	var last := (T.size() - 1) * seg
	for cap in [[Vector3(0, 0, -0.53), 0, Vector3.FORWARD], [Vector3(0, 0, 0.31), last, Vector3.BACK]]:
		var c0 := vs.size()
		vs.append(cap[0])
		ns.append(cap[2])
		cs.append(cs[cap[1] + 2])
		for i in seg:
			ix.append_array([c0, cap[1] + i, cap[1] + (i + 1) % seg])
	# хвостовой плавник: вилка в вертикальной (у камбалы — горизонтальной) плоскости
	var span := 0.55 * h if not flat else 0.14
	var ax := Vector3.UP if not flat else Vector3.RIGHT
	var fin_n := Vector3.RIGHT if not flat else Vector3.UP
	var fc := back * 0.8
	var t0 := vs.size()
	for pt in [Vector3(0, 0, 0.27), ax * span + Vector3(0, 0, 0.5), Vector3(0, 0, 0.43), -ax * span + Vector3(0, 0, 0.5)]:
		vs.append(pt)
		ns.append(fin_n)
		cs.append(fc)
	ix.append_array([t0, t0 + 1, t0 + 2, t0, t0 + 2, t0 + 3])
	if not flat:                             # спинной плавник над кольцами 2-4
		var d0 := vs.size()
		for r in [2, 3, 4]:
			var top: Vector3 = vs[r * seg + 2]
			vs.append(top)
			vs.append(top + Vector3(0, 0.45 * h * (1.2 - 0.3 * (r - 2)), 0.04))
			ns.append_array([fin_n, fin_n])
			cs.append_array([fc, fc])
		for k in 2:
			var b := d0 + k * 2
			ix.append_array([b, b + 1, b + 3, b, b + 3, b + 2])
	return _mesh(vs, ns, cs, ix)


## Краб шириной 1 (клешни к −Z): панцирь, 4 пары ног, 2 клешни.
func _crab_mesh(col: Color) -> ArrayMesh:
	var vs := PackedVector3Array()
	var ns := PackedVector3Array()
	var cs := PackedColorArray()
	var ix := PackedInt32Array()
	vs.append(Vector3(0, 0.26, 0))
	ns.append(Vector3.UP)
	cs.append(col * 1.1)
	for i in 10:
		var q := TAU * i / 10
		vs.append(Vector3(0.5 * cos(q), 0.12, 0.36 * sin(q) - 0.04 * absf(cos(q))))
		ns.append(Vector3(cos(q), 1.2, sin(q)).normalized())
		cs.append(col * (0.8 + 0.3 * _hash(i)))
	vs.append(Vector3(0, 0.06, 0))
	ns.append(Vector3.DOWN)
	cs.append(col * 1.6)
	for i in 10:
		var j := (i + 1) % 10
		ix.append_array([0, 1 + j, 1 + i, 11, 1 + i, 1 + j])
	var leg_c := col * 1.25
	for sd in [-1.0, 1.0]:
		for k in 4:
			var z := -0.12 + k * 0.11
			_strip(vs, ns, cs, ix, [Vector3(sd * 0.42, 0.1, z), Vector3(sd * 0.78, 0.24, z + 0.04 * (k - 1.5)),
					Vector3(sd * 0.98, -0.05, z + 0.09 * (k - 1.5))], 0.045, leg_c)
		_strip(vs, ns, cs, ix, [Vector3(sd * 0.28, 0.12, -0.3), Vector3(sd * 0.46, 0.17, -0.52),
				Vector3(sd * 0.22, 0.12, -0.68)], 0.1, col * 0.9)
	return _mesh(vs, ns, cs, ix)


## Лента по точкам pts шириной w (горизонтально поперёк хода), двусторонняя (шейдер без отсечения).
func _strip(vs: PackedVector3Array, ns: PackedVector3Array, cs: PackedColorArray, ix: PackedInt32Array,
		pts: Array, w: float, col: Color) -> void:
	var b := vs.size()
	for k in pts.size():
		var p: Vector3 = pts[k]
		var t: Vector3 = (pts[mini(k + 1, pts.size() - 1)] - pts[maxi(k - 1, 0)]).normalized()
		var sd := t.cross(Vector3.UP).normalized() * w * 0.5
		vs.append_array([p - sd, p + sd])
		var n := sd.cross(t).normalized()
		ns.append_array([n, n])
		cs.append_array([col, col])
	for k in pts.size() - 1:
		var o := b + k * 2
		ix.append_array([o, o + 2, o + 1, o + 1, o + 2, o + 3])


static func _mesh(vs: PackedVector3Array, ns: PackedVector3Array, cs: PackedColorArray, ix: PackedInt32Array) -> ArrayMesh:
	var arr := []
	arr.resize(Mesh.ARRAY_MAX)
	arr[Mesh.ARRAY_VERTEX] = vs
	arr[Mesh.ARRAY_NORMAL] = ns
	var uv := PackedVector2Array()                 # цвет в UV/UV2: COLOR в пачках Compatibility занят данными экземпляра
	var uv2 := PackedVector2Array()
	for c in cs:
		uv.append(Vector2(c.r, c.g))
		uv2.append(Vector2(c.b, 0.0))
	arr[Mesh.ARRAY_TEX_UV] = uv
	arr[Mesh.ARRAY_TEX_UV2] = uv2
	arr[Mesh.ARRAY_INDEX] = ix
	var m := ArrayMesh.new()
	m.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
	return m
