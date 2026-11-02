extends SceneTree
## Проверки правил уровней без окна:
##   Godot_console --headless --path godot --script res://tests/game_tests.gd
## Кольца (как RingCourse.cs сборки): проход по оси, обратный проход, облёт, порядок (+15),
## пропуск к финишу (+30), финиш на 6-м, касания без штрафа с паузой 0,4 с, таблица лидеров.
## Осмотр судна: дальность 3 м, угол 35°, 1,5 с подряд.

var failures := 0


func check(name: String, ok: bool) -> void:
	print(("OK   " if ok else "FAIL ") + name)
	if not ok:
		failures += 1


## Точка на оси кольца i: s вдоль оси (м), r поперёк (м, по горизонтали).
func at(i: int, s: float, r := 0.0) -> PackedFloat64Array:
	var c := RingCourse.center(i)
	var a := RingCourse.axis(i)
	return PackedFloat64Array([c[0] + a[0] * s - a[1] * r, c[1] + a[1] * s + a[0] * r, c[2]])


func pass_ring(rc: RingCourse, i: int, t: float, r := 0.0, back := false) -> void:
	var s0 := 0.5 if back else -0.5
	rc.tick(at(i, s0, 6.0), t - 0.2)     # подход сбоку, далеко от кольца: смена стороны там не считается
	rc.tick(at(i, s0, r), t)
	rc.tick(at(i, -s0, r), t + 0.1)


func _init() -> void:
	var rc := RingCourse.new()
	rc.begin(at(0, -3.0), 0.0)
	pass_ring(rc, 0, 1.0)
	check("кольцо 1 по оси взято", rc.passed[0] and rc.out_of_order == 0)
	pass_ring(rc, 1, 2.0, 0.0, true)
	check("обратный проход не засчитан", not rc.passed[1] and rc.event.contains("обратную"))
	pass_ring(rc, 1, 3.0, 1.0)
	check("облёт рядом (1 м при просвете 1,1) не засчитан, сообщение", not rc.passed[1] and rc.event.contains("обойдено"))
	pass_ring(rc, 2, 4.0)
	check("кольцо 3 раньше 2: засчитано, +15", rc.passed[2] and rc.out_of_order == 1 and rc.penalty() == 15 + 4 * 30)
	pass_ring(rc, 0, 5.0)
	check("повтор: «уже взято», без штрафа", rc.event.contains("уже взято") and rc.out_of_order == 1)
	rc.contact(4, 5.1)
	rc.contact(4, 5.3)
	rc.contact(0, 5.6)
	check("касания с паузой 0,4 с: 2 из 3, штрафа нет", rc.touches == 2 and rc.ring_touches[3] == 1)
	pass_ring(rc, 5, 60.0)
	check("финиш на кольце 6 (не по порядку)", rc.phase == RingCourse.Phase.FINISHED and rc.out_of_order == 2)
	check("не взяты 2, 4, 5: +90; итог = время + 2·15 + 3·30",
			rc.missed() == 3 and rc.penalty() == 120 and absf(rc.total() - (60.1 + 120)) < 1e-6)
	var res := rc.result("тест")
	check("поля результата как leaders_rings.json", res.has_all(["name", "total", "time", "penalty", "missed",
			"out_of_order", "touches", "date"]))
	var tmp := OS.get_user_data_dir().path_join("test_leaders")
	DirAccess.make_dir_recursive_absolute(tmp)
	for f in ["leaders_rings.json", "rings_results.csv"]:
		if FileAccess.file_exists(tmp.path_join(f)):
			DirAccess.remove_absolute(tmp.path_join(f))
	RingCourse.save_result({"name": "б", "total": 200.0, "time": 200.0, "penalty": 0, "missed": 0,
			"out_of_order": 0, "touches": 0, "date": "x"}, tmp)
	var top := RingCourse.save_result(res, tmp)
	check("таблица отсортирована по итогу", top.size() == 2 and top[0]["name"] == "тест")
	check("CSV: заголовок + 2 строки", FileAccess.get_file_as_string(tmp.path_join("rings_results.csv")).split("\n", false).size() == 3)

	# все кольца по порядку
	var rc2 := RingCourse.new()
	rc2.begin(at(0, -3.0), 0.0)
	for i in 6:
		pass_ring(rc2, i, 10.0 * (i + 1))
	check("6 колец по порядку: штраф 0, итог = время", rc2.penalty() == 0 and absf(rc2.total() - 60.1) < 1e-6)

	# осмотр судна
	var sv := WreckSurvey.new()
	var pts: Array = [Vector3(0, 0, -2.0)]
	sv.points = pts
	sv.names = ["тест"]
	sv.start(Vector3.ZERO, 0.0)
	var cam := Transform3D()        # смотрит в −Z
	sv.tick(Transform3D(Basis(), Vector3(0, 0, 0.6)), 0.0, func(_a, _b): return true)
	check("смещение 0,5 м от старта запускает время", sv.started)
	for k in 100:
		sv.tick(cam, 0.02 * k, func(_a, _b): return true)
	check("точка в 2 м на оси, 1,98 с: осмотрена", sv.done[0])
	var sv2 := WreckSurvey.new()
	sv2.points = [Vector3(0, 0, -3.2)]
	sv2.names = ["далеко"]
	sv2.start(Vector3(0, 0, 1), 0.0)
	for k in 200:
		sv2.tick(cam, 0.02 * k, func(_a, _b): return true)
	check("дальше 3 м: не осмотрена", not sv2.done[0])
	var sv3 := WreckSurvey.new()
	sv3.points = [Vector3(-2.0 * sin(deg_to_rad(36)), 0, -2.0 * cos(deg_to_rad(36)))]
	sv3.names = ["сбоку"]
	sv3.start(Vector3(0, 0, 1), 0.0)
	for k in 200:
		sv3.tick(cam, 0.02 * k, func(_a, _b): return true)
	check("36° от оси камеры: не осмотрена", not sv3.done[0])
	var sv4 := WreckSurvey.new()
	sv4.points = [Vector3(0, 0, -2.0)]
	sv4.names = ["заслонена"]
	sv4.start(Vector3(0, 0, 1), 0.0)
	for k in 200:
		sv4.tick(cam, 0.02 * k, func(_a, _b): return false)
	check("заслонена: не осмотрена", not sv4.done[0])
	var sv5 := WreckSurvey.new()
	sv5.points = [Vector3(0, 0, -2.0)]
	sv5.names = ["мигает"]
	sv5.start(Vector3(0, 0, 1), 0.0)
	for k in 200:
		var seen := (k / 50) % 2 == 0       # 1 с видна, 1 с нет
		sv5.tick(cam, 0.02 * k, func(_a, _b): return seen)
	check("видна по 1 с с перерывами: не осмотрена (нужно 1,5 с подряд)", not sv5.done[0])

	_pult_tests()
	_results_tests()
	print("ИТОГ:", "все проверки пройдены" if failures == 0 else "%d не пройдено" % failures)
	quit(1 if failures > 0 else 0)


## S4: управление как у пульта (протокол пульта, docs/ui.md). Клавиатура и геймпад дают те же
## команды, что кадр пульта: оба движителя по микшированию правого стика, цистерны u/d по выбору LT/RT.
func _pult_tests() -> void:
	var m := func(st: Vector2i): return RovControl.joystick_to_motors(st.x, st.y)
	check("↑: оба движителя вперёд 100", m.call(PultInput.keyboard_stick(true, false, false, false)) == PackedInt32Array([100, 100]))
	check("↓: оба назад −100", m.call(PultInput.keyboard_stick(false, true, false, false)) == PackedInt32Array([-100, -100]))
	check("→: поворот вправо, левый +100, правый −100", m.call(PultInput.keyboard_stick(false, false, false, true)) == PackedInt32Array([100, -100]))
	check("↑+→: L = y + x, R = y − x с нормировкой -> [100, 0]", m.call(PultInput.keyboard_stick(true, false, false, true)) == PackedInt32Array([100, 0]))
	check("геймпад: ось Y Godot вниз -> XInput вверх", PultInput.pad_stick(0.0, -1.0) == Vector2i(0, 32767))
	check("геймпад: внутри зоны 15000 движители стоят", m.call(PultInput.pad_stick(0.4, -0.45)) == PackedInt32Array([0, 0]))
	check("цистерны: без LT/RT пульт ничего не шлёт", PultInput.tank_command(true, false, false, false) == PackedInt32Array([0, 0]))
	check("цистерны: ↑ + LT = u только цистерне 1", PultInput.tank_command(true, false, true, false) == PackedInt32Array([1, 0]))
	check("цистерны: ↓ + LT + RT = d обеим", PultInput.tank_command(false, true, true, true) == PackedInt32Array([-1, -1]))
	check("шаги цели глубины 10/50/100/500 мм", PultInput.DEPTH_STEPS == [0.010, 0.050, 0.100, 0.500])
	PultInput.ensure_actions()
	# одна физическая клавиша — одно действие (кроме V и Shift+V)
	var seen := {}
	var dup := []
	for a in InputMap.get_actions():
		if String(a).begins_with("ui_") or a == "pip_cam":
			continue
		for e in InputMap.action_get_events(a):
			if e is InputEventKey:
				var k: int = e.physical_keycode
				if seen.has(k):
					dup.append("%s: %s и %s" % [OS.get_keycode_string(k), seen[k], a])
				seen[k] = a
	check("у клавиш нет двойных назначений" + ("" if dup.is_empty() else " (" + ", ".join(dup) + ")"), dup.is_empty())
	# крена и бокового хода нет ни в одном действии
	var names := ", ".join(PultInput.KEYS.keys())
	check("нет команд крена и бокового смещения", not names.contains("roll") and not names.contains("sway") and not names.contains("heave"))
	Settings.override_from_args({"filters": "0", "style_scale": "2", "pip": true})
	check("настройки из командной строки: --filters 0 --style_scale 2 --pip",
			Settings.get_value("filters") == false and Settings.get_value("style_scale") == 2 and Settings.get_value("pip") == true)


## S7: таблица колец (JSON + CSV, 10 лучших) и осмотра судна (CSV), во временной папке.
func _results_tests() -> void:
	var dir := "user://test_results_tmp"
	DirAccess.make_dir_recursive_absolute(dir)
	for f in ["leaders_rings.json", "rings_results.csv", "wreck_results.csv"]:
		DirAccess.remove_absolute(dir.path_join(f))
	for k in 12:
		RingCourse.save_result({"name": "п%d" % k, "total": 300.0 - k, "time": 290.0 - k, "penalty": 10, "missed": 0,
				"out_of_order": 0, "touches": k, "date": "2026-11-02 12:%02d" % k}, dir)
	var top := ResultsTable.load_rings(dir)
	check("кольца: в таблице 10 лучших, первый с наименьшим итогом", top.size() == 10 and float(top[0]["total"]) == 289.0)
	var csv := FileAccess.get_file_as_string(dir.path_join("rings_results.csv")).strip_edges().split("\n")
	check("кольца: CSV с заголовком и 12 строками", csv.size() == 13 and csv[0].begins_with("name;total;time;penalty"))
	ResultsTable.save_wreck({"name": "а", "time": 120.5, "points": 6, "touches": 2, "date": "2026-11-02 12:00"}, dir)
	ResultsTable.save_wreck({"name": "б", "time": 95.0, "points": 6, "touches": 0, "date": "2026-11-02 12:05"}, dir)
	var w := ResultsTable.load_wreck(dir)
	check("судно: CSV читается, лучший по времени первым", w.size() == 2 and w[0]["name"] == "б" and is_equal_approx(w[0]["time"], 95.0))
