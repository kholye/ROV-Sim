class_name Tether
extends Node3D
## Кабель-трос аппарата (версия 1.2) и граница места крушения. Мост «движок <-> физика кабеля»:
##  - физика — physics/tether_cable.gd (NED, без узлов; эталон physics_ref/rov/tether.py, источники —
##    docs/physics-sources.md, разд. 30): кабель от блока судна обеспечения над местом (origin на поверхности)
##    к кормовому гермовводу №2; помощник на судне стравливает и выбирает его, предел — tether_length_max;
##  - здесь: шаг кабеля каждый кадр физики после аппарата, сила кабеля -> аппарат (Rov.ext_force, RK4 этапа 2),
##    течение у узлов (как у аппарата), касания узлов с дном и судном — лучом от старого положения к новому
##    (только у дна и у судна), трубка для вида, признаки «зацеп» и «предел» для экрана;
##  - мутность у края места (оценка, оформление границы, разд. 28): дальше TURBID_FROM м от судна рассеяние
##    взвесью растёт до ×TURBID_MAX к TURBID_TO м, поэтому края сцены не видно.

const TURBID_FROM := 14.5      # старт аппарата в 14 м от судна — ещё в обычной воде
const TURBID_TO := 20.5
const TURBID_MAX := 7.0
const RADIUS := 0.0035         # радиус кабеля для касаний и вида, м (пучок Ø5,1 + Ø2,8 мм)
const SIDES := 5               # граней у трубки
const VIEW := 12.0             # м: дальше от камеры звенья не рисуются (видимость у судна ≈ 7 м)
const MAX_SEG := 64            # звеньев не больше (22 м / 0,5 м = 44 + запас)
const SETTLE := 4.0            # с: кабель успокаивается перед стартом
const SNAG_FORCE := 3.0        # Н: натяжение у аппарата, при котором кабель на судне считается зацепом (оценка)

var level: LevelBase
var rov: Rov
var origin := Vector3.ZERO
var center := Vector3.ZERO
var cable: TetherCable
var snag := false              # кабель лежит на судне (не на дне) и держит аппарат
var at_limit := false          # стравлен весь и натянут
var _k := 1.0
var _attach := PackedFloat64Array()
var _seabed_depth := 0.0
var _zone := AABB()            # где искать касания, кроме дна (Godot)
var _space: PhysicsDirectSpaceState3D
var _wreck_touch := 0
var _dbg := Vector3i.ZERO      # вызовов, лучей, попаданий (журнал --cable_log)
var _mesh: MultiMeshInstance3D
var _mm: MultiMesh
var _mat: ShaderMaterial


## Вызывать после add_child (нужен мир для лучей). origin — блок на судне обеспечения (на поверхности, откуда идёт
## кабель); center_ — середина места (мутность); seabed_depth — глубина дна; zone — объём, где кабель может задеть
## судно и предметы (Godot).
func setup(lvl: LevelBase, origin_: Vector3, center_: Vector3, seabed_depth: float, zone: AABB, with_cable := true) -> void:
	level = lvl
	rov = lvl.rov
	origin = origin_
	center = center_
	_seabed_depth = seabed_depth
	_zone = zone
	name = "Tether"
	if not with_cable:
		return
	process_physics_priority = 10          # после аппарата (его шаг уже сделан в этом кадре)
	var p := rov.p
	_attach = PackedFloat64Array(p["tether_attach"])
	var end := attach_ned()
	var a := NedGodot.vec_to_ned(origin)
	var d := sqrt((end[0] - a[0]) ** 2 + (end[1] - a[1]) ** 2 + (end[2] - a[2]) ** 2)
	var sl: Array = p["tether_slack"]
	var L0 := minf(float(p["tether_length_max"]), maxf(float(sl[0]) * d + float(sl[1]), d + float(p["tether_seg"])))
	cable = TetherCable.new(p, a, end, L0)
	var cyl := CylinderMesh.new()            # единичный: радиус 1, длина 1 (масштаб — в матрице звена)
	cyl.top_radius = 1.0
	cyl.bottom_radius = 1.0
	cyl.height = 1.0
	cyl.radial_segments = SIDES
	cyl.rings = 0
	cyl.cap_top = false
	cyl.cap_bottom = false
	_mat = Underwater.material(Vector3(0.12, 0.12, 0.13))   # серая оболочка витой пары с чёрным коаксиалом (оценка)
	cyl.material = _mat
	_mm = MultiMesh.new()
	_mm.transform_format = MultiMesh.TRANSFORM_3D
	_mm.mesh = cyl
	_mm.instance_count = MAX_SEG
	_mm.visible_instance_count = 0
	_mesh = MultiMeshInstance3D.new()
	_mesh.multimesh = _mm
	_mesh.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_mesh.custom_aabb = AABB(Vector3(-100, -100, -100), Vector3(200, 200, 200))
	add_child(_mesh)
	_space = get_world_3d().direct_space_state
	var n := int(SETTLE * Engine.physics_ticks_per_second)      # кабель успокаивается, аппарат пока стоит
	for i in n:
		_step(1.0 / Engine.physics_ticks_per_second)


## Конец кабеля на аппарате (гермоввод №2), NED.
func attach_ned() -> PackedFloat64Array:
	var x := rov.x
	var R := RovDynamics.rot_nb(x[3], x[4], x[5])
	var out := PackedFloat64Array([x[0], x[1], x[2]])
	for i in 3:
		out[i] += R[i * 3] * _attach[0] + R[i * 3 + 1] * _attach[1] + R[i * 3 + 2] * _attach[2]
	return out


func _physics_process(dt: float) -> void:
	if cable == null:
		_edge_turbidity()
		return
	_step(dt)
	var te := cable.tension_end
	if rov.kinematic:
		rov.ext_force = PackedFloat64Array()
	else:
		rov.ext_force = PackedFloat64Array([te[0], te[1], te[2], _attach[0], _attach[1], _attach[2]])
	var f := sqrt(te[0] * te[0] + te[1] * te[1] + te[2] * te[2])
	at_limit = cable.taut
	snag = _wreck_touch > 0 and f > SNAG_FORCE and not at_limit
	if level.args.has("cable_log") and fmod(rov.time, 1.0) < dt:   # --cable_log: раз в секунду состояние кабеля
		var vmax := 0.0
		var zmin := 1e9
		var imax := 0
		for i in cable.count():
			var vi := Vector3(cable.V[3 * i], cable.V[3 * i + 1], cable.V[3 * i + 2]).length()
			if vi > vmax:
				vmax = vi
				imax = i
			zmin = minf(zmin, cable.X[3 * i + 2])
		print("CABLE t=%.1f узлов %d стравлено %.2f м, у аппарата %.2f Н, у судна %.2f Н, |v| макс %.2f м/с, выше всех %.2f м, касаний %d (судно %d)%s%s" % [
				rov.time, cable.count(), cable.length, f, cable.tension_top, vmax, zmin, cable.contacts.size(), _wreck_touch,
				" ЗАЦЕП" if snag else "", " ПРЕДЕЛ" if at_limit else ""])
		var pts := []
		for i in range(0, cable.count(), 8):
			pts.append("(%.1f %.1f %.1f)" % [cable.X[3 * i], cable.X[3 * i + 1], cable.X[3 * i + 2]])
		var lo := Vector3(1e9, 1e9, 1e9)
		var hi := -lo
		var nan := 0
		for i in cable.count():
			var v := Vector3(cable.X[3 * i], cable.X[3 * i + 1], cable.X[3 * i + 2])
			if is_nan(v.x) or is_nan(v.y) or is_nan(v.z):
				nan += 1
			lo = lo.min(v)
			hi = hi.max(v)
		print("  рамка ", lo, " ", hi, " NaN ", nan, "  аппарат: глубина %.2f, дифферент %.1f°, сила кабеля NED (%.2f %.2f %.2f), цистерны %.0f/%.0f мл" % [
				rov.x[2], rad_to_deg(rov.x[4]), te[0], te[1], te[2], rov.x[12] * 1e6, rov.x[13] * 1e6])
		print("  узлы ", " ".join(pts), " rest0 %.3f" % cable.rest[0], " вызовов/лучей/попаданий ", _dbg, " быстрый узел ", imax,
				" касания ", cable.contacts)
		_dbg = Vector3i.ZERO
	_edge_turbidity()


## Мутность у края места (оформление границы, разд. 28).
func _edge_turbidity() -> void:
	var cam := rov.camera().global_position
	var h := Vector2(cam.x - center.x, cam.z - center.z).length()
	var k := 1.0 + (TURBID_MAX - 1.0) * smoothstep(TURBID_FROM, TURBID_TO, h)
	if level.args.has("clear"):              # --clear: без взвеси (только для показа кабеля на снимках)
		k = 0.02
	if absf(k - _k) > 0.005:
		_k = k
		level.uw.set_turbidity(k, rov.light)


func _step(dt: float) -> void:
	var end := attach_ned()
	_wreck_touch = 0
	cable.payout(dt, end)
	cable.step(dt, end, _water, _contact)


func _water(X: PackedFloat64Array) -> PackedFloat64Array:
	return rov.water_velocity(X[2])


## Касание узла: луч от старого положения к новому (Godot); узлы далеко от дна и вне зоны судна не проверяются.
func _contact(xo: PackedFloat64Array, xn: PackedFloat64Array) -> Array:
	var b := NedGodot.vec(xn)
	_dbg.x += 1
	if xn[2] < _seabed_depth - 1.5 and not _zone.has_point(b):
		return []
	_dbg.y += 1
	var a := NedGodot.vec(xo)
	var q := PhysicsRayQueryParameters3D.create(a, b + (b - a).normalized() * RADIUS if a != b else b + Vector3(0, -RADIUS, 0))
	q.collision_mask = 1
	var hit := _space.intersect_ray(q)
	if hit.is_empty():
		return []
	_dbg.z += 1
	var nrm: Vector3 = hit["normal"]
	var pos: Vector3 = hit["position"] + nrm * RADIUS
	var depth := maxf((pos - b).dot(nrm), 0.0)
	var col := hit["collider"] as Node
	if col and col.get_parent() and String(col.get_parent().name) != "Seabed":
		_wreck_touch += 1
	return [NedGodot.vec_to_ned(pos), NedGodot.vec_to_ned(nrm), depth]


func _process(_dt: float) -> void:
	if cable == null:
		return
	var N := cable.count()
	var cam := get_viewport().get_camera_3d()
	var eye := cam.global_position if cam else rov.global_position
	var rad := RADIUS * float(level.args.get("cable_width", 1.0))   # --cable_width k: толще только на снимках
	# звено — отрезок цилиндра (MultiMesh): ось Y на звено, длина — масштаб; дальше VIEW м от камеры не рисуется
	var prev := NedGodot.vec(cable.node(0))
	var n := 0
	for i in range(1, N):
		var cur := NedGodot.vec(cable.node(i)) if i < N - 1 else rov.to_global(NedGodot.vec(_attach))
		var mid := (prev + cur) * 0.5
		var d := cur - prev
		var L := d.length()
		if L > 1e-4 and mid.distance_to(eye) < VIEW and n < MAX_SEG:
			var y := d / L
			var x := y.cross(Vector3.UP)
			if x.length() < 0.1:
				x = y.cross(Vector3.RIGHT)
			x = x.normalized()
			var z := x.cross(y)
			_mm.set_instance_transform(n, Transform3D(Basis(x * rad, y * L, z * rad), mid))
			n += 1
		prev = cur
	_mm.visible_instance_count = n


## Для экрана: стравлено, натяжение у аппарата.
func length() -> float:
	return cable.length if cable else 0.0


func tension() -> float:
	if cable == null:
		return 0.0
	var te := cable.tension_end
	return sqrt(te[0] * te[0] + te[1] * te[1] + te[2] * te[2])
