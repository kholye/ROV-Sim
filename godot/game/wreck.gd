extends LevelBase
## Затонувшее судно в мутной воде. Правила и расстановка по первой версии симулятора (Семенов Н. Н.), само место — из Blender: blender/build_wreck_site.py -> wreck_site.glb
## (дно 40 × 40 м на 8 м с наносами ила и размывом, судно-скан «Malpas Metal Boat Wreck», artfletch,
## CC BY 4.0, якорь с цепью, бочки, камни, водоросли и сидячая живность; точки осмотра — пустые объекты IP_*).
## Придонное течение (rov_params.json, current_wreck_*) и ил от движителей (game/silt_cloud.gd).
## Обрастание и живность на дне — экземплярами (game/wreck_life.gd), рыбы, камбала и крабы — game/fauna.gd
## (места Home_* из той же сцены). Кабель-трос с физикой и граница места (мутная вода у края) — game/tether.gd.
## Шесть точек осмотра (WreckSurvey): 3 м, 35°, не заслонена, 1,5 с подряд. Каждая осмотренная точка
## сохраняет кадр; в конце отчёт (время, кадры, касания) в survey/<дата>/ папки данных (Paths).

const SEABED := 8.0
## Блок кабеля на судне обеспечения (Godot): на поверхности в 6 м к югу от середины судна, в сторону старта, —
## не над корпусом (иначе кабель с начала лежит на обломках); дальняя точка осмотра — 16,1 м по прямой.
const SHIP := Vector3(0, 0, 6)
const WRECK_GLB := preload("res://assets/wreck/wreck_site.glb")

var survey := WreckSurvey.new()
var wreck: Node3D
var tether: Tether
const FOULING := 0.85         # обрастание корпуса в шейдере (налёт и «ковры» мелких актиний), оценка
const NO_COLLIDE := ["Bio_", "Fine_", "Proto_"]   # водоросли, мелочь и образцы не мешают ходу
const FINE_RANGE := 13.0      # мелочь на дне по ячейкам 6 м: дальше не рисуется (вода мутная)
var out_dir := ""
var shots := {}
var _auto_path: Array = []
var _auto_i := 0
var _auto_hold := 0.0


func _ready() -> void:
	place = "wreck"
	setup_level("wreck", "wreck_e_surface")
	wreck = WRECK_GLB.instantiate()
	wreck.position = Vector3(0, -SEABED, 0)
	add_child(wreck)
	uw.convert_tree(wreck)
	for mi: MeshInstance3D in wreck.find_children("*", "MeshInstance3D", true, false):
		if not NO_COLLIDE.any(func(pre): return mi.name.begins_with(pre)):
			mi.create_trimesh_collision()
		if mi.name.begins_with("Fine_"):
			mi.visibility_range_end = FINE_RANGE
		if mi.name == "WreckHull":
			for s in mi.mesh.get_surface_count():
				(mi.get_surface_override_material(s) as ShaderMaterial).set_shader_parameter("fouling", FOULING)
	if not args.has("no-life"):              # --no-life / --no-fauna: без обрастания / рыб (замеры)
		WreckLife.build(wreck)
	var ips := wreck.find_children("IP_*", "", true, false)
	ips.sort_custom(func(a, b): return String(a.name) < String(b.name))
	for n in ips:
		survey.points.append((n as Node3D).global_position)
		survey.names.append(String(n.name).substr(5))
	spawn_rov(4.0, -14.0, 0.0, 0.0)          # старт как в сборке: z = −14 м, глубина 4 м
	var pc := rov.p                          # придонное течение (rov_params.json, current_wreck_*)
	var T: float = pc["current_wreck_T"]
	rov.current = RovEnvironment.Current.new(pc["current_wreck_speed"], deg_to_rad(pc["current_wreck_dir_deg"]),
			T, float(pc["current_wreck_std"]) * sqrt(2.0 / T), 3)
	rov.seabed_depth = SEABED
	if not args.has("no-silt"):              # --no-silt: без ила от движителей (замеры)
		var silt := SiltCloud.new()
		add_child(silt)
		silt.setup(rov, PackedFloat64Array([0, 0, SEABED]), 30.0)
	if not args.has("no-fauna"):
		var fauna := Fauna.new()
		add_child(fauna)
		fauna.setup(rov, wreck, Vector3(0, -SEABED, 0))
	tether = Tether.new()
	add_child(tether)
	tether.setup(self, SHIP, Vector3(0, -SEABED, 0), SEABED,   # блок судна обеспечения на поверхности рядом с местом
			AABB(Vector3(-13, -SEABED - 1, -13), Vector3(26, 8, 26)),     # судно, якорь, бочки, камни
			not args.has("no-tether"))       # --no-tether: без физики и вида кабеля (замеры), мутность у края остаётся
	if audio:
		audio.tether = tether                # шорох кабеля о судно
	rov.touched.connect(func(_c): survey.contact(rov.time))
	var tan_h := tan(deg_to_rad(rov.cam_front.fov) * 0.5)        # камера аппарата держит ширину (KEEP_WIDTH)
	var vp := get_viewport().get_visible_rect().size
	survey.frame_tan = Vector2(tan_h, tan_h * vp.y / vp.x)
	survey.lens = rov.lens                                       # «в кадре» — по проекции объектива DiCam 300
	survey.frame_h = vp.y / vp.x
	survey.start(rov.cam_front.global_position, 0.0)
	out_dir = Paths.dir("survey") + Time.get_datetime_string_from_system().replace(":", "-")
	if args.has("auto"):
		_plan_auto()
	elif args.has("path"):                   # --path "n,e,d;…": автопилот проверок по точкам (показ кабеля и ила)
		var ap: RefCounted = load("res://tests/path_autopilot.gd").new()
		ap.attach(rov, String(args["path"]))
		rov.input_enabled = false
		rov.autopilot = func(r): return ap.stick(r)


## Точка не заслонена и различима: доля света от самой поверхности (альбедо 0,15, нормаль к камере) в яркости
## пикселя не меньше SIGNAL_MIN по той же модели света (лампа, свет сверху, пелена воды). В воде у судна
## (видимость 7 м) с лампой это ≈ до 1,7 м, без лампы ≈ до 1,1 м (оценка, docs/levels.md).
const SIGNAL_MIN := 0.2


func _visible(from: Vector3, to: Vector3) -> bool:
	var q := PhysicsRayQueryParameters3D.create(from, to)
	q.collision_mask = 1
	var hit := get_world_3d().direct_space_state.intersect_ray(q)
	if not (hit.is_empty() or (hit["position"] as Vector3).distance_to(to) < 0.35):
		return false
	return surface_signal(from, to) >= SIGNAL_MIN


func surface_signal(cam: Vector3, p: Vector3) -> float:
	var n := (cam - p).normalized()
	var lo := rov.light.radiance(cam, p, n, Vector3(0.15, 0.15, 0.15))
	var lv := rov.light.radiance(cam, p, n, Vector3.ZERO)
	var yo := 0.299 * lo.x + 0.587 * lo.y + 0.114 * lo.z
	var yv := 0.299 * lv.x + 0.587 * lv.y + 0.114 * lv.z
	return 1.0 - yv / maxf(yo, 1e-12)


func _physics_process(delta: float) -> void:
	if rov == null:
		return
	if args.has("auto"):
		_auto_step(delta)
		if fmod(rov.time, 5.0) < delta * 0.999:
			print("AUTO t=%.0f шаг %d/%d камера %s точки %s видна %s" % [rov.time, _auto_i, _auto_path.size(),
					rov.cam_front.global_position.snappedf(0.01), survey.done, survey.seen_for])
	var was := survey.finished()
	survey.tick(rov.cam_front.global_transform, rov.time, _visible)    # осматривает камера аппарата, не вид сзади
	if survey.just_done >= 0:
		_shoot(survey.just_done)
	if not was and survey.finished():
		_report()


func _shoot(i: int) -> void:
	var hud_was := hud.visible
	hud.visible = false                      # кадр без интерфейса
	await get_tree().process_frame
	await RenderingServer.frame_post_draw
	DirAccess.make_dir_recursive_absolute(out_dir)
	var path := out_dir.path_join("IP_%d.png" % (i + 1))
	get_viewport().get_texture().get_image().save_png(path)
	hud.visible = hud_was
	shots[i] = path
	if audio:
		audio.beep()


func _report() -> void:
	await get_tree().create_timer(0.3).timeout      # дождаться последнего кадра
	DirAccess.make_dir_recursive_absolute(out_dir)
	var rows := []
	var md := "# Отчёт осмотра судна\n\nВремя осмотра: %.1f с. Касаний судна и дна: %d.\n\n| № | Точка | Время, с | Кадр |\n|---|---|---|---|\n" % [
		survey.elapsed(rov.time), survey.touches]
	var csv := "n;point;time_s;frame\n"
	for i in survey.points.size():
		var f := String(shots.get(i, "")).get_file()
		md += "| %d | %s | %.1f | ![](%s) |\n" % [i + 1, survey.names[i], survey.done_time[i], f]
		csv += "%d;%s;%.1f;%s\n" % [i + 1, survey.names[i], survey.done_time[i], f]
		rows.append({"n": i + 1, "point": survey.names[i], "time": snappedf(survey.done_time[i], 0.1), "frame": f})
	var fm := FileAccess.open(out_dir.path_join("report.md"), FileAccess.WRITE)
	fm.store_string(md)
	fm.close()
	var fc := FileAccess.open(out_dir.path_join("report.csv"), FileAccess.WRITE)
	fc.store_string(csv)
	fc.close()
	var res := {"name": String(args.get("name", Settings.get_value("player"))), "time": snappedf(survey.elapsed(rov.time), 0.1),
			"points": survey.count(), "touches": survey.touches, "mode": rov.control_mode,
			"date": Time.get_datetime_string_from_system().replace("T", " ").substr(0, 16)}
	ResultsTable.save_wreck(res)
	hud.results.show_wreck(ResultsTable.load_wreck("", rov.control_mode), res, "Отчёт и кадры: %s · Esc — меню" % Paths.shown(out_dir))
	hud.results.visible = true
	print("SURVEY ", JSON.stringify({"dir": Paths.shown(out_dir), "time": snappedf(survey.elapsed(rov.time), 0.1),
			"touches": survey.touches, "points": rows}))
	if args.has("auto"):
		get_tree().quit()


## Автопроверка осмотра (кинематика, без физики): облёт точек обзора около каждой точки осмотра.
## Проверяет правила осмотра, заслонение, кадры и отчёт; управляемость аппарата проверена на кольцах.
func _plan_auto() -> void:
	rov.kinematic = true
	rov.input_enabled = false
	# точка обзора: 1,1 м от точки осмотра в сторону от середины судна (по горизонтали) и на 0,4 м выше
	var center := Vector3(0, -SEABED + 1.5, 0)
	var pos := rov.global_position
	for i in survey.points.size():
		var target: Vector3 = survey.points[i]
		var away := Vector3(target.x - center.x, 0, target.z - center.z)
		away = away.normalized() if away.length() > 0.3 else Vector3.BACK
		var view: Vector3 = target + away * 1.1 + Vector3.UP * 0.4
		_auto_path.append([Vector3(pos.x, -2.5, pos.z), target])     # подняться над судном
		_auto_path.append([Vector3(view.x, -2.5, view.z), target])
		_auto_path.append([view, target])
		pos = view


func _auto_step(delta: float) -> void:
	if _auto_i >= _auto_path.size():
		if rov.time > 400:
			print("SURVEY_TIMEOUT ", survey.done)
			get_tree().quit()
		return
	var goal: Vector3 = _auto_path[_auto_i][0]
	var look: Vector3 = _auto_path[_auto_i][1]
	var p := rov.cam_front.global_position
	var step := 1.5 * delta
	if p.distance_to(goal) <= step:
		p = goal
		_auto_hold += delta
		if _auto_hold > 2.0 or (_auto_i % 3 != 2):
			_auto_i += 1
			_auto_hold = 0.0
	else:
		p += (goal - p).normalized() * step
	var d := (look - p).normalized()
	var psi := atan2(d.x, -d.z)                 # курс NED: от севера (−Z) к востоку (+X)
	var theta := asin(clampf(d.y, -1, 1)) + deg_to_rad(rov.cam_tilt)   # дифферент: нос вверх > 0; камера наклонена вниз
	rov.x[3] = 0.0
	rov.x[4] = theta
	rov.x[5] = psi
	# камера впереди центра аппарата: ставим центр так, чтобы камера оказалась в p
	var cam_world := NedGodot.basis(rov.x) * rov.cam_front.position
	var ned := NedGodot.vec_to_ned(p - cam_world)
	rov.x[0] = ned[0]
	rov.x[1] = ned[1]
	rov.x[2] = ned[2]


func hud_mission() -> String:
	var t := "ОСМОТР %d / %d\n%s с" % [survey.count(), survey.points.size(), Hud.num(survey.elapsed(rov.time), 1)]
	# ближайшая неосмотренная точка
	var best := -1
	var cam := rov.cam_front.global_position
	for i in survey.points.size():
		if not survey.done[i] and (best < 0 or cam.distance_to(survey.points[i]) < cam.distance_to(survey.points[best])):
			best = i
	if best >= 0:
		t += "\nближе всего: %s, %s м" % [survey.names[best], Hud.num(cam.distance_to(survey.points[best]), 1)]
	if tether:
		t += "\nкабель %s / %s м, %s Н" % [Hud.num(tether.length(), 1), Hud.num(float(rov.p["tether_length_max"]), 0),
				Hud.num(tether.tension(), 1)]
	return t


func hud_prompt() -> String:
	if tether and tether.at_limit:
		return "КАБЕЛЬ СТРАВЛЕН ДО ПРЕДЕЛА (%s м) и держит аппарат — вернитесь к судну" % Hud.num(tether.length(), 0)
	if tether and tether.snag:
		return "КАБЕЛЬ ЗАЦЕПИЛСЯ (натяжение %s Н) — отойдите назад по своему следу" % Hud.num(tether.tension(), 1)
	if survey.finished():
		return "ОСМОТР ЗАВЕРШЁН за %s с" % Hud.num(survey.elapsed(rov.time), 1)
	if not survey.started:
		return "отойдите на 0,5 м от старта — пойдёт время"
	var cam := rov.cam_front.global_transform
	for i in survey.points.size():
		if not survey.done[i] and survey.seen_for[i] > 0.0:
			return "%s в кадре: держите %s с" % [survey.names[i], Hud.num(maxf(WreckSurvey.HOLD - survey.seen_for[i], 0.0), 1)]
	for i in survey.points.size():                  # в кадре, но не различима: подсказать почему
		if not survey.done[i] and survey.in_frame(cam, survey.points[i]) and cam.origin.distance_to(survey.points[i]) < 4.0:
			if cam.origin.distance_to(survey.points[i]) >= WreckSurvey.RANGE or surface_signal(cam.origin, survey.points[i]) < SIGNAL_MIN:
				return "%s: плохо видно — ближе%s" % [survey.names[i], "" if rov.lamp_level > 0.0 else " и включите лампу (L)"]
	return ""
