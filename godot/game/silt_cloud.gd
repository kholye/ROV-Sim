class_name SiltCloud
extends Node
## Мост «движок <-> физика ила»: шаг SiltPlume (physics/silt_plume.gd, NED) по состоянию аппарата,
## глубина дна под движителями — лучом вниз по столкновениям сцены (дно, ил, палуба — всё считается илистым,
## оценка), клубы -> шейдер (Underwater.set_silt, дымка) и модель света аппарата (автоэкспозиция, осмотр),
## пятна размыва и струи -> частицы-хлопья (game/silt_flocs.gd).
## Перевод NED -> Godot только через NedGodot.

const DT := 0.05                   # шаг облака, с (20 Гц: клубы движутся медленно)
const RAY := 3.0                   # дно ищется не дальше, м

var rov: Rov
var plume: SiltPlume
var flocs: SiltFlocs           # видимые хлопья (частицы на видеокарте), та же физика
var site := PackedFloat64Array([0, 0, 0])   # середина места (NED): клубы дальше radius убираются
var radius := 30.0
var _acc := 0.0
var _log := OS.get_cmdline_user_args().has("--silt_log")   # --silt_log: раз в секунду итог облака в журнал
var _t_step := 0
var _max_draw := SiltPlume.MAX_PUFFS
var _no_cpu := OS.get_cmdline_user_args().has("--silt_no_cpu")   # замеры: без ила в модели света на процессоре
var _t_set := 0
var _n_steps := 0


func setup(rov_: Rov, site_ned := PackedFloat64Array([0, 0, 0]), radius_ := 30.0) -> void:
	rov = rov_
	site = site_ned
	radius = radius_
	plume = SiltPlume.new(rov.p, float(rov.uw.p["silt_b_star"]))
	if not OS.get_cmdline_user_args().has("--no-flocs"):   # --no-flocs: без частиц-хлопьев (замеры)
		flocs = SiltFlocs.new()
		rov.get_parent().add_child(flocs)
		flocs.setup(rov.uw, rov.p)
	var a := OS.get_cmdline_user_args()
	var i := a.find("--silt_draw")            # --silt_draw n: свету отдать не больше n клубов (замеры)
	if i >= 0 and i + 1 < a.size():
		_max_draw = int(a[i + 1])
	name = "SiltCloud"


func _physics_process(delta: float) -> void:
	if rov == null or rov.kinematic:
		return
	_acc += delta
	if _acc < DT:
		return
	var dt := _acc
	_acc = 0.0
	var t0 := Time.get_ticks_usec()
	plume.step(dt, rov.x, rov.thr, _beds(), rov.current, rov.seabed_depth)
	plume.cull(site, radius)
	if flocs:
		var cur := rov.current.velocity() if rov.current else PackedFloat64Array([0, 0, 0])
		flocs.update(plume, plume.jets(rov.x, rov.thr), cur, rov.seabed_depth)
	var t1 := Time.get_ticks_usec()
	var out := []
	for f in plume.puffs:
		out.append({"c": NedGodot.vec(f.pos), "m": f.m, "sh": f.sh, "sv": f.sz, "bed": -f.bed,
				"b": f.peak_c() * plume.b_star})
	if out.size() > _max_draw:               # свету — самые плотные клубы
		out.sort_custom(func(a, b): return a["b"] > b["b"])
		out.resize(_max_draw)
	Underwater.set_silt(out)
	rov.light.silt = [] if _no_cpu else out
	if _log:
		_t_step += t1 - t0
		_t_set += Time.get_ticks_usec() - t1
		_n_steps += 1
	if _log and fmod(rov.time, 1.0) < dt:
		var bmax := 0.0
		for f in plume.puffs:
			bmax = maxf(bmax, f.peak_c() * 2.0 * plume.b_star)
		var bc := plume.concentration(NedGodot.vec_to_ned(rov.camera().global_position)) * plume.b_star
		print("SILT t=%.1f клубов %d во взвеси %.2f г размыто %.2f г пик b %.2f 1/м, у камеры b %.2f 1/м; шаг %.2f мс, раздача %.2f мс" % [rov.time,
				plume.puffs.size(), plume.suspended() * 1000.0, plume.eroded * 1000.0, bmax, bc,
				_t_step / 1000.0 / maxi(_n_steps, 1), _t_set / 1000.0 / maxi(_n_steps, 1)])
		_t_step = 0
		_t_set = 0
		_n_steps = 0


## Глубина дна (NED, м) под срезом каждого движителя; NAN — дна в пределах RAY нет.
func _beds() -> PackedFloat64Array:
	var beds := PackedFloat64Array([NAN, NAN])
	var space := rov.get_world_3d().direct_space_state
	var tp: Array = rov.p["thruster_pos"]
	for k in 2:
		var sgn := -1.0 if k == 0 else 1.0
		var from := rov.to_global(NedGodot.vec(PackedFloat64Array([float(tp[0]), sgn * float(tp[1]), float(tp[2])])))
		var q := PhysicsRayQueryParameters3D.create(from, from + Vector3(0, -RAY, 0))
		q.collision_mask = 1
		var hit := space.intersect_ray(q)
		if not hit.is_empty():
			beds[k] = -(hit["position"] as Vector3).y
	return beds


func _exit_tree() -> void:
	Underwater.set_silt([])
