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
	{"x": [3, -1, 6.0, 0.1, -0.2, 2.0, 0.3, 0.05, -0.02, 0.1, -0.1, 0.2, 40e-6, 30e-6],
			"thr": [0.5, 0.2], "vc": [0.08, 0.03, 0], "dropped": false, "ext": [-2.0, 0.7, -0.4, -0.35, 0.0, -0.028]},
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
				PackedFloat64Array(st["vc"]), st["dropped"], PackedFloat64Array(st.get("ext", [])))
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

	# ---- 5) профиль течения у дна (те же значения, что physics_ref/rov/environment.py, bed_profile) ----
	check("профиль течения: 1 м над дном при 8 м = (1/2,56)^(1/7)",
			absf(RovEnvironment.bed_profile(1.0, 8.0) - pow(1.0 / 2.56, 1.0 / 7.0)) < 1e-12)
	check("профиль течения: у дна 0, выше 0,5 h — 1,07",
			RovEnvironment.bed_profile(0.0, 8.0) == 0.0 and RovEnvironment.bed_profile(5.0, 8.0) == 1.07)
	var cur := RovEnvironment.Current.new(0.1, 0.3)
	var va := cur.velocity_at(1.0, 8.0)
	check("течение на высоте: velocity × профиль", absf(va[0] - 0.1 * cos(0.3) * pow(1.0 / 2.56, 1.0 / 7.0)) < 1e-12)

	# ---- 6) ил (тот же сценарий, что physics_ref/verify/v7_silt.py, часть (ж)): CSV рядом с V2 ----
	var sp := SiltPlume.new(p)
	var cur0 := RovEnvironment.Current.new(p["current_wreck_speed"], deg_to_rad(p["current_wreck_dir_deg"]))
	var xs6 := RovDynamics.initial_state(8.0 - 0.15 - float(p["thruster_pos"][2]), 0.3)
	xs6[4] = deg_to_rad(4.0)
	var t6 := Time.get_ticks_usec()
	for i in 600:
		var th := PackedFloat64Array([1.0, 0.8]) if i < 100 else (PackedFloat64Array([-0.6, -0.6]) if i < 150 else PackedFloat64Array([0, 0]))
		sp.step(0.1, xs6, th, PackedFloat64Array([8.0, 8.0]), cur0, 8.0)
	print("ил: 600 шагов %.1f мс, клубов %d" % [(Time.get_ticks_usec() - t6) / 1000.0, sp.puffs.size()])
	var fs := FileAccess.open(out_path.get_basename() + "_silt.csv", FileAccess.WRITE)
	fs.store_line("%s,%s,%s,%s" % [var_to_str(sp.eroded), var_to_str(sp.deposited), var_to_str(sp.removed), var_to_str(sp.suspended())])
	for pf in sp.puffs:
		fs.store_line(",".join([var_to_str(pf.pos[0]), var_to_str(pf.pos[1]), var_to_str(pf.pos[2]), var_to_str(pf.m),
				var_to_str(pf.sh), var_to_str(pf.sz)]))
	fs.close()
	var bal := absf(sp.suspended() + sp.deposited + sp.removed - sp.eroded) / maxf(sp.eroded, 1e-30)
	check("ил: баланс масс < 1e-12 (размыто %.2f г)" % (sp.eroded * 1000.0), sp.eroded > 0.0 and bal < 1e-12)

	# ---- 7) кабель (тот же сценарий, что physics_ref/verify/v8_tether.py, часть (д)) ----
	var tdt := 1.0 / 120.0
	var tend := PackedFloat64Array([6.0, 2.0, 7.0])
	var tc := TetherCable.new(p, PackedFloat64Array([0, 0, 0]), tend, 11.0)
	var wat := func(_x): return PackedFloat64Array([0.1, 0.05, 0.0])
	var bed := func(xo: PackedFloat64Array, xn: PackedFloat64Array) -> Array:
		if xn[2] > 8.0:
			return [PackedFloat64Array([xn[0], xn[1], 8.0]), PackedFloat64Array([0, 0, -1.0]), xn[2] - 8.0]
		return []
	var t7 := Time.get_ticks_usec()
	for i in 240:                          # 2 с: дальше трение покоя/скольжения раздувает разницу округлений (V8)
		tend[0] += 0.2 * tdt
		tend[1] += 0.1 * tdt
		tc.payout(tdt, tend)
		tc.step(tdt, tend, wat, bed)
	print("кабель: 240 шагов %.1f мс, узлов %d, стравлено %.2f м" % [(Time.get_ticks_usec() - t7) / 1000.0, tc.count(), tc.length])
	var ft := FileAccess.open(out_path.get_basename() + "_tether.csv", FileAccess.WRITE)
	ft.store_line("%s,%s,%s" % [var_to_str(tc.tension_end[0]), var_to_str(tc.tension_end[1]), var_to_str(tc.tension_end[2])])
	for i in tc.count():
		ft.store_line("%s,%s,%s" % [var_to_str(tc.X[3 * i]), var_to_str(tc.X[3 * i + 1]), var_to_str(tc.X[3 * i + 2])])
	ft.close()
	var lerr := absf(tc.total_length() - tc.length)
	check("кабель: длина звеньев = стравленной (%.1f нм)" % (lerr * 1e9), lerr < 1e-9)

	print("ИТОГ: ", "все проверки пройдены" if failures == 0 else "%d проверок не пройдено" % failures)
	quit(1 if failures > 0 else 0)


func _row(t: float, x: PackedFloat64Array) -> String:
	var parts := PackedStringArray([String.num(t, 3)])
	for i in 14:
		parts.append("%.15f" % x[i])
	return ",".join(parts)
