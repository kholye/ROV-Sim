extends LevelBase
## Игровой бассейн с 6 кольцами (размеры и раскладка из первой версии симулятора).
## Модель из Blender: blender/build_pool.py -> assets/pool/pool.glb (чаша 12 × 25 × 5 м в плитке, разметка
## дорожек, лоток, лестницы, иллюминаторы, 10 подводных светильников, кольца с ножками и номерами).
## Вода спортивного бассейна (чистая, видимость ≈29 м), свет сверху 300 лк с каустикой, подводные
## светильники как неподвижные источники шейдера.
## Enter: старт заплыва (время пошло), Backspace: вернуть на старт. Итог пишется в user://leaders_rings.json
## и user://rings_results.csv, на финише — таблица 10 лучших на экране.

const W := 12.0      # восток (X Godot)
const L := 25.0      # север (−Z Godot)
const DEPTH := 5.0
const POOL_GLB := preload("res://assets/pool/pool.glb")

var course := RingCourse.new()
var player := "игрок"
var top10: Array = []
var _ring_of_body := {}
var _autopilot: RefCounted     # держим ссылку: Callable её не держит
var _n_events := 0
var _event_t := -10.0


func _ready() -> void:
	setup_level("swimpool", "pool_e_surface")
	_build_pool()
	var s: Array = RingCourse.START
	spawn_rov(s[2], s[0], s[1], s[3])
	rov.touched.connect(_on_touch)
	course.restart(rov.position_ned())
	player = String(args.get("name", Settings.get_value("player")))
	if args.has("auto"):
		_autopilot = load("res://tests/ring_autopilot.gd").new()
		var ap := _autopilot
		rov.input_enabled = false
		rov.autopilot = Callable(ap, "stick")
		ap.call("attach", rov)
		course.begin(rov.position_ned(), rov.time)


func _build_pool() -> void:
	var pool := POOL_GLB.instantiate()
	add_child(pool)
	uw.convert_tree(pool)
	var lights := []
	var p := uw.p
	var m: float = p["pool_light_m"]
	var I0: float = float(p["pool_light_flux"]) * (m + 1.0) / TAU
	for mi in pool.find_children("*", "MeshInstance3D", true, false):
		var n := String(mi.name)
		if n.begins_with("PoolLight_") and not n.ends_with("_ring"):
			var pos: Vector3 = mi.global_position
			lights.append({"pos": pos, "i": Underwater.v3(p["pool_light_rgb"]) * I0,
					"dir": Vector3(-signf(pos.x), 0, 0), "m": m})
		if n.begins_with("Lane") or n.begins_with("Target") or n.begins_with("DepthStripe") or n.contains("_num_"):
			continue                                 # разметка лежит на стенах: столкновения не нужны
		(mi as MeshInstance3D).create_trimesh_collision()
		if n.begins_with("Ring_"):
			var body := mi.get_child(mi.get_child_count() - 1)
			_ring_of_body[body] = int(n.split("_")[1])
	Underwater.set_static_lights([] if args.has("no-lights") else lights)
	Underwater.set_caustics(float(p["pool_caustics"]))
	# поверхность воды снизу: яркость неба под водой ≈ E/π (оценка)
	LevelKit.quad(self, Vector2(W + 0.6, L + 0.6), Transform3D(Basis(Vector3.RIGHT, PI / 2), Vector3.ZERO),
			Underwater.material(Vector3.ZERO, uw.esurf / PI))


func _on_touch(collider: Object) -> void:
	course.contact(_ring_of_body.get(collider, 0), rov.time)


func _unhandled_input(ev: InputEvent) -> void:
	super(ev)
	if not ev.is_pressed() or ev.is_echo():
		return
	if ev.is_action("start_run") and course.phase != RingCourse.Phase.RUNNING:
		_reset_rov()
		course.begin(rov.position_ned(), rov.time)
		hud.results.visible = false
	elif ev.is_action("reset_run"):
		_reset_rov()
		course.restart(rov.position_ned())
		hud.results.visible = false


func _reset_rov() -> void:
	var s: Array = RingCourse.START
	rov.x = RovDynamics.initial_state(s[2], deg_to_rad(s[3]))
	rov.x[0] = s[0]
	rov.x[1] = s[1]
	rov.dropped = false
	rov.emergency = false
	rov.depth_hold = false
	rov.battery = RovEnvironment.Battery.new(rov.p)


func _physics_process(_delta: float) -> void:
	if rov == null:
		return
	var was := course.phase
	course.tick(rov.position_ned(), rov.time)
	if was == RingCourse.Phase.RUNNING and course.phase == RingCourse.Phase.FINISHED:
		var res := course.result(player)
		res["mode"] = rov.control_mode
		top10 = RingCourse.save_result(res)
		hud.results.show_rings(top10, res, "Ваш итог %s · Enter — новый заплыв · Esc — меню" % Hud.num(res["total"], 1))
		hud.results.visible = true
		print("RINGS ", JSON.stringify(res))
		print("RINGS_EVENTS ", JSON.stringify(course.events))
		if args.has("auto"):
			get_tree().quit()
	if args.has("auto") and fmod(rov.time, 10.0) < _delta * 0.999:
		print("AUTO t=%.0f N=%.2f E=%.2f D=%.2f psi=%.0f u=%.2f V=%.0f/%.0f мл цель %.2f" % [rov.time, rov.x[0], rov.x[1],
				rov.x[2], rov.heading_deg(), rov.x[6], rov.x[12] * 1e6, rov.x[13] * 1e6, rov.depth_target])
	if args.has("auto") and rov.time > float(args.get("timeout", 1500)):
		print("RINGS_TIMEOUT ", JSON.stringify({"time": rov.time, "next": course.next_number(), "events": course.events}))
		get_tree().quit()


func _process(delta: float) -> void:
	super(delta)
	if course.events.size() != _n_events:
		_n_events = course.events.size()
		_event_t = rov.time
		if audio:
			audio.beep()


func hud_mission() -> String:
	match course.phase:
		RingCourse.Phase.RUNNING:
			return "КОЛЬЦО %d / 6\n%s с  +%d\nкасаний %d" % [course.next_number(), Hud.num(course.elapsed(rov.time), 1),
					course.penalty() - course.missed() * RingCourse.MISS_PENALTY, course.touches]
		RingCourse.Phase.FINISHED:
			return "ФИНИШ\nитог %s\n%s с + %d" % [Hud.num(course.total(), 1), Hud.num(course.elapsed(0), 1), course.penalty()]
	return "КОЛЬЦА · %s\n6 колец по порядку" % player


func hud_prompt() -> String:
	if course.phase == RingCourse.Phase.WAITING:
		return "Enter — старт заплыва"
	if course.event != "" and rov.time - _event_t < 4.0:
		return course.event
	return ""
