extends SceneTree
## Проверки физики в Godot без окна:
##   Godot_console --headless --path godot --script res://tests/physics_tests.gd -- <выход.csv>
## 1) прогон V2 (тот же сценарий, что physics_ref/verify/v2_compare.py), запись CSV каждые 0,1 с;
## 2) модуль перевода NED -> Godot; 3) микширование и сетка ПИД; 4) время шага.

var failures := 0


func check(name: String, ok: bool) -> void:
	print(("OK   " if ok else "FAIL ") + name)
	if not ok:
		failures += 1


## Сценарий V2 по номеру отрезка 0,1 с (целые, чтобы моменты переключения совпадали точно).
static func schedule(seg: int) -> Dictionary:
	var thr: PackedFloat64Array
	if seg < 100: thr = PackedFloat64Array([0.6, 0.6])
	elif seg < 200: thr = PackedFloat64Array([0.8, -0.2])
	elif seg < 300: thr = PackedFloat64Array([0.0, 0.0])
	elif seg < 450: thr = PackedFloat64Array([-0.5, -0.3])
	else: thr = PackedFloat64Array([0.3, 0.7])
	var tank: PackedInt32Array
	if seg < 150: tank = PackedInt32Array([1, 0])
	elif seg < 300: tank = PackedInt32Array([0, -1])
	elif seg < 450: tank = PackedInt32Array([-1, -1])
	else: tank = PackedInt32Array([1, 1])
	return {"thr": thr, "tank": tank}


## Те же состояния в physics_ref/verify/v2_compare.py (DERIV_STATES).
const DERIV_STATES := [
	{"x": [1, 2, 1.5, 0.2, -0.15, 0.7, 0.4, -0.1, 0.05, 0.3, -0.2, 0.25, 60e-6, 10e-6],
			"thr": [0.7, -0.4], "vc": [0.1, -0.05, 0.02], "dropped": false},
	{"x": [0, 0, 2.0, -0.1, 0.2, -1.0, -0.2, 0.15, -0.1, -0.1, 0.3, -0.2, 20e-6, 50e-6],
			"thr": [-0.3, 0.9], "vc": [0, 0, 0], "dropped": true},
	{"x": [0, 0, 0.5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 35e-6, 35e-6],
			"thr": [0, 0], "vc": [0, 0, 0], "dropped": true},
]


func _init() -> void:
	var args := OS.get_cmdline_user_args()
	var out_path: String = args[0] if args.size() > 0 else "user://v2_godot.csv"
	var p := RovDynamics.load_params()
	var dyn := RovDynamics.new(p)

	# ---- 1) V2 ----
	var dt := 0.005
	var steps_per_seg := 20
	var x := RovDynamics.initial_state(1.0, 0.3, 50e-6, 20e-6)
	var vc := PackedFloat64Array([0.1, 0.05, 0.0])
	var f := FileAccess.open(out_path, FileAccess.WRITE)
	f.store_line("t,x,y,z,phi,theta,psi,u,v,w,p,q,r,V1,V2")
	var t_phys := 0
	for seg in 600:
		f.store_line(_row(seg * 0.1, x))
		var s := schedule(seg)
		var t0 := Time.get_ticks_usec()
		for k in steps_per_seg:
			x = dyn.rk4_step(x, dt, s["thr"], s["tank"], vc)
		t_phys += Time.get_ticks_usec() - t0
	f.store_line(_row(60.0, x))
	f.close()
	var us_per_step := float(t_phys) / (600 * steps_per_seg)
	print("V2 CSV: ", ProjectSettings.globalize_path(out_path))
	print("время шага RK4: %.1f мкс (нужно < 5000 мкс для 200 Гц в реальном времени)" % us_per_step)

	# ---- 1б) производные в состояниях, которых нет в V2 (в том числе после сброса груза) ----
	var fd := FileAccess.open(out_path.get_basename() + "_deriv.csv", FileAccess.WRITE)
	for st in DERIV_STATES:
		var xs := PackedFloat64Array(st["x"])
		var d := dyn.deriv(xs, PackedFloat64Array(st["thr"]), PackedInt32Array([0, 0]),
				PackedFloat64Array(st["vc"]), st["dropped"])
		var cells := []
		for i in 20:
			cells.append(var_to_str(d[i]))
		fd.store_line(",".join(cells))
	fd.close()

	# ---- 2) перевод NED -> Godot ----
	var e := 1e-6
	check("север -> -Z", NedGodot.vec(PackedFloat64Array([1, 0, 0])).is_equal_approx(Vector3(0, 0, -1)))
	check("восток -> +X", NedGodot.vec(PackedFloat64Array([0, 1, 0])).is_equal_approx(Vector3(1, 0, 0)))
	check("вниз -> -Y", NedGodot.vec(PackedFloat64Array([0, 0, 1])).is_equal_approx(Vector3(0, -1, 0)))
	var xs := RovDynamics.initial_state(2.0, PI / 2)
	var b := NedGodot.basis(xs)
	check("курс 90°: нос смотрит на восток (+X)", (b * Vector3(0, 0, -1)).distance_to(Vector3(1, 0, 0)) < e)
	check("глубина 2 м -> Y = -2", absf(NedGodot.position(xs).y + 2.0) < e)
	xs = RovDynamics.initial_state(0.0)
	xs[4] = deg_to_rad(10.0)
	b = NedGodot.basis(xs)
	check("дифферент +10°: нос вверх", (b * Vector3(0, 0, -1)).y > 0.17)
	xs = RovDynamics.initial_state(0.0)
	xs[3] = deg_to_rad(10.0)
	b = NedGodot.basis(xs)
	check("крен +10°: правый борт вниз", (b * Vector3(1, 0, 0)).y < -0.17)
	xs = RovDynamics.initial_state(0.0)
	xs[3] = 0.4; xs[4] = -0.3; xs[5] = 2.1
	b = NedGodot.basis(xs)
	check("базис ортонормирован, det = +1", b.is_equal_approx(b.orthonormalized()) and absf(b.determinant() - 1.0) < e)
	var v := PackedFloat64Array([0.3, -0.7, 1.1])
	var back := NedGodot.vec_to_ned(NedGodot.vec(v))
	check("vec_to_ned(vec(v)) = v", absf(back[0] - v[0]) + absf(back[1] - v[1]) + absf(back[2] - v[2]) < e)

	# ---- 3) управление ----
	check("стик вперёд -> 100/100", RovControl.joystick_to_motors(0, 32767) == PackedInt32Array([100, 100]))
	check("стик вправо -> 100/-100", RovControl.joystick_to_motors(32767, 0) == PackedInt32Array([100, -100]))
	check("мёртвая зона", RovControl.joystick_to_motors(14999, -14999) == PackedInt32Array([0, 0]))
	check("сетка ПИД 0,25 -> 0,3", is_equal_approx(RovControl.quantize_gain(0.25), 0.3))
	check("сетка ПИД 12 -> 9,9", is_equal_approx(RovControl.quantize_gain(12.0), 9.9))

	# ---- 4) нейтральный в покое ----
	var xr := RovDynamics.initial_state(1.5)
	for i in 2000:
		xr = dyn.rk4_step(xr, 0.05, PackedFloat64Array([0, 0]), PackedInt32Array([0, 0]))
	check("нейтральный 100 с в покое: |dz| < 1e-9", absf(xr[2] - 1.5) < 1e-9)

	print("ИТОГ: ", "все проверки пройдены" if failures == 0 else "%d проверок не пройдено" % failures)
	quit(1 if failures > 0 else 0)


func _row(t: float, x: PackedFloat64Array) -> String:
	var parts := PackedStringArray([String.num(t, 3)])
	for i in 14:
		parts.append("%.15f" % x[i])
	return ",".join(parts)
