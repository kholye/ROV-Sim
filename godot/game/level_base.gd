class_name LevelBase
extends Node3D
## Общее для уровней: подводный свет, аппарат, экран оператора (Hud), стиль (StylePass), пауза,
## звук, режимы запуска для проверок. Уровень сообщает экрану задание (hud_mission) и подсказку (hud_prompt).
## Аргументы после «--»:
##   --bench <с>     замер кадров/с: аппарат идёт по кругу с лампой, печатает BENCH {...} и выходит
##   --shot <png>    кадр через 20 кадров, затем выход (снимки для docs/); --shot_t <с> — кадр на этой секунде
##   --stir t,x,y    стик пульта (x, y) t секунд, затем отпущен: ил у дна для снимков
##   --auto          автопилот проверки (у уровня свой: кольца / осмотр судна), печатает итог и выходит
##   --chase         вид сзади вместо камеры аппарата
##   --no-hud        без интерфейса и окошка (снимки сцены);  --show help / pause: справка или пауза открыты
##   --filters 0/1, --pip 0/1, --forces 0/1, --graph 0/1, --light_curve 0/1, --vsync 0/1, --style_scale 2/3:
##                   настройки на один запуск (game/settings.gd), в файл не пишутся

var uw: Underwater
var rov: Rov
var hud: Hud
var style: StylePass
var pause: PauseMenu
var audio: RovAudio
var args := {}
var _frames := 0
var _shot_done := false
var _lens_set := false
var _bench_t := 0.0
var _bench_fps: Array[float] = []
var _bench_ms: Array[float] = []


func _parse_args() -> void:
	var a := OS.get_cmdline_user_args()
	var i := 0
	while i < a.size():
		var k := a[i].trim_prefix("--")
		if i + 1 < a.size() and not a[i + 1].begins_with("--"):
			args[k] = a[i + 1]
			i += 2
		else:
			args[k] = true
			i += 1


func setup_level(water: String, e_surface_key: String, surface_y := 0.0) -> void:
	_parse_args()
	Settings.override_from_args(args)
	if args.has("auto") or args.has("bench") or args.has("stir") or args.has("path"):     # проверки, замеры и снимки — в научном режиме
		Settings.override_from_args({"control": "science"})
	Settings.apply_global()
	PultInput.ensure_actions()
	uw = Underwater.new(water, e_surface_key)
	uw.apply_globals(surface_y)
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	env.environment.background_mode = Environment.BG_COLOR
	env.environment.background_color = Color.BLACK
	env.environment.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	env.environment.ambient_light_source = Environment.AMBIENT_SOURCE_DISABLED
	env.environment.reflected_light_source = Environment.REFLECTION_SOURCE_DISABLED
	add_child(env)
	style = StylePass.new()
	add_child(style)


func spawn_rov(depth: float, north: float, east: float, psi_deg: float) -> void:
	rov = Rov.new()
	rov.name = "Rov"
	add_child(rov)
	rov.setup(uw, depth, north, east, psi_deg)
	if not args.has("no-particles"):
		var sus := Suspension.new()
		sus.rov = rov
		add_child(sus)
		sus.setup(uw, uw.bp550, 5.0)
	if args.has("at"):                       # --at север,восток,глубина,курс (NED, м и °)
		var v := String(args["at"]).split_floats(",")
		rov.x = RovDynamics.initial_state(v[2], deg_to_rad(v[3]))
		rov.x[0] = v[0]
		rov.x[1] = v[1]
		rov.reset_control()
		rov._sync()
	if args.has("record"):                   # --record: запись телеметрии с первого кадра (как F9)
		rov.telemetry.start(0.0)
	if args.has("lamp"):
		rov.lamp_level = float(args["lamp"])
	if args.has("chase"):
		rov.cam_chase.current = true
	if args.has("cam"):                      # --cam x,y,z --look x,y,z (Godot): обзорная камера для снимков
		var c := String(args["cam"]).split_floats(",")
		var l := String(args.get("look", "0,-2,0")).split_floats(",")
		var cam := Camera3D.new()
		cam.fov = 70.0
		cam.far = 150.0                      # сфера воды 50 м вокруг аппарата целиком в кадре
		add_child(cam)
		cam.look_at_from_position(Vector3(c[0], c[1], c[2]), Vector3(l[0], l[1], l[2]))
		cam.current = true
	hud = Hud.new()
	add_child(hud)
	hud.setup(self, rov)
	hud.visible = not args.has("no-hud")
	pause = PauseMenu.new()
	add_child(pause)
	pause.setup(self)
	audio = RovAudio.new()
	add_child(audio)
	audio.setup(rov)
	apply_settings()
	match String(args.get("show", "")):        # --show help / pause: для снимков экрана
		"help":
			hud.help.visible = true
		"pause":
			pause.visible = true             # без остановки дерева: иначе снимок не сделается
			pause._main()
	if args.has("stir"):                     # --stir t,x,y: стик (единицы пульта) t секунд, затем отпущен (снимки ила)
		var st := String(args["stir"]).split_floats(",")
		rov.input_enabled = false
		rov.autopilot = func(r): return [st[1], st[2]] if r.time < st[0] else [0, 0]
	if args.has("bench"):
		rov.input_enabled = false
		rov.autopilot = func(_r): return [9000 + 16000, 32767]   # полный ход с поворотом
		rov.lamp_level = 1.0


## Задание справа вверху (уровень переопределяет).
func hud_mission() -> String:
	return ""


## Подсказка по центру под прицелом (уровень переопределяет); сообщения аппарата важнее.
func hud_prompt() -> String:
	return ""


func apply_settings() -> void:
	style.set_on(bool(Settings.get_value("filters")))
	if args.has("scale3d"):                # доля разрешения 3D для замеров
		get_viewport().scaling_3d_mode = Viewport.SCALING_3D_MODE_BILINEAR
		get_viewport().scaling_3d_scale = float(args["scale3d"])
	if hud:
		hud.apply_settings()


func _unhandled_input(ev: InputEvent) -> void:
	if hud == null or not ev.is_pressed() or ev.is_echo():
		return
	if ev.is_action("filters"):
		Settings.toggle("filters")
		apply_settings()
		get_viewport().set_input_as_handled()
	elif hud.handle(ev):
		get_viewport().set_input_as_handled()


func _process(delta: float) -> void:
	_frames += 1
	if style and rov:                        # объектив DiCam 300 — только у камеры аппарата
		style.set_lens(get_viewport().get_camera_3d() == rov.cam_front, null if _lens_set else rov.lens)
		_lens_set = true
	RenderingServer.global_shader_parameter_set("uw_time", Time.get_ticks_msec() / 1000.0)
	var shot_now := rov != null and rov.time >= float(args["shot_t"]) if args.has("shot_t") else _frames == 20
	if args.has("shot") and shot_now and not _shot_done:
		_shot_done = true
		get_viewport().get_texture().get_image().save_png(String(args["shot"]))
		get_tree().quit()
	if args.has("bench"):
		_bench_ms.append(delta * 1000.0)
		_bench_t += delta
		if _bench_t > 2.0:     # первые 2 с прогрев (компиляция шейдеров)
			_bench_fps.append(1.0 / maxf(delta, 1e-6))
		if _bench_t >= 2.0 + float(args["bench"]):
			var s := _bench_fps.duplicate()
			s.sort()
			var avg := s.size() / (_bench_t - 2.0)
			var p1: float = s[int(s.size() * 0.01)]
			var p5: float = s[int(s.size() * 0.05)]
			print("BENCH ", JSON.stringify({"scene": scene_file_path, "seconds": _bench_t - 2.0, "frames": s.size(),
					"fps_avg": snappedf(avg, 0.1), "fps_p5": snappedf(p5, 0.1), "fps_p1": snappedf(p1, 0.1),
					"fps_min": snappedf(s[0], 0.1), "size": get_viewport().get_visible_rect().size,
					"draw_calls": RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_DRAW_CALLS_IN_FRAME),
					"primitives": RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_PRIMITIVES_IN_FRAME),
					"cpu_process_ms": snappedf(Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0, 0.01),
					"cpu_physics_ms": snappedf(Performance.get_monitor(Performance.TIME_PHYSICS_PROCESS) * 1000.0, 0.01)}))
			get_tree().quit()
