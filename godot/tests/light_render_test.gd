extends Node3D
## Проверка порта света: шейдер Godot против эталона physics_ref/rov/light.py (V5, часть «порт»).
## Запуск с окном (нужен рендер):
##   Godot --path godot res://tests/light_render_test.tscn -- --out <файл.json>
## Для каждой конфигурации рисует 10 секторов планшета перед камерой, берёт пиксель в центре
## каждого сектора (среднее блока 8×8 из-за дизеринга) и пишет в JSON вместе с геометрией (луч, дальность, нормаль, лампа, вода).
## Сравнение делает physics_ref/verify/v5_godot.py.

const W := 1280
const H := 720
const HFOV := 54.0
# (имя, вода, дальность, база лампы, мощность, глубина камеры, свет сверху)
const CASES := [
	["pool_d1_b01", "pool", 1.0, 0.1, 0.5, 1.5, false],
	["pool_d2_b05", "pool", 2.0, 0.5, 0.5, 1.5, false],
	["pool_d27_b05_100", "pool", 2.7, 0.5, 1.0, 1.5, false],
	["pool_d2_b05_amb", "pool", 2.0, 0.5, 0.5, 2.5, true],
	["turbid_d15_b02", "turbid", 1.5, 0.2, 0.5, 4.0, true],
	["pool_amb_only", "pool", 2.0, 0.5, 0.0, 2.0, true],
]

var out_path := "user://light_render_test.json"
var cam: Camera3D
var plate: Node3D
var results := []
var case_i := -1
var wait := 0
var uw: Underwater
var albedo: Array


func _ready() -> void:
	var args := OS.get_cmdline_user_args()
	var i := args.find("--out")
	if i >= 0 and i + 1 < args.size():
		out_path = args[i + 1]
	get_window().size = Vector2i(W, H)
	albedo = Underwater.load_params()["plate_albedo_rgb"]
	cam = Camera3D.new()
	cam.keep_aspect = Camera3D.KEEP_WIDTH
	cam.fov = HFOV
	cam.far = 60.0
	add_child(cam)
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	env.environment.background_mode = Environment.BG_COLOR
	env.environment.background_color = Color.BLACK
	env.environment.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	add_child(env)
	plate = Node3D.new()
	add_child(plate)
	for k in 10:
		var q := MeshInstance3D.new()
		var m := QuadMesh.new()
		m.size = Vector2(0.12, 0.06)
		q.mesh = m
		var al: Array = albedo[k]
		q.material_override = Underwater.material(Vector3(al[0], al[1], al[2]))
		q.position = Vector3((k % 2 - 0.5) * 0.14, (2 - k / 2) * 0.08, 0.0)
		q.name = "S%d" % (k + 1)
		plate.add_child(q)
	_next_case()


func _next_case() -> void:
	case_i += 1
	if case_i >= CASES.size():
		var f := FileAccess.open(out_path, FileAccess.WRITE)
		f.store_string(JSON.stringify({"width": W, "height": H, "hfov_deg": HFOV, "cases": results}, "  "))
		f.close()
		print("записано ", out_path)
		get_tree().quit()
		return
	var cs: Array = CASES[case_i]
	uw = Underwater.new(cs[1])
	uw.esurf = uw.esurf if cs[6] else Vector3.ZERO
	uw.apply_globals(0.0, 0.004)
	var depth: float = cs[5]
	cam.position = Vector3(0, -depth, 0)
	plate.position = Vector3(0, -depth, -float(cs[2]))
	var I: Vector3 = uw.lamp_intensity("sdvs5", cs[4]) if cs[4] > 0 else Vector3.ZERO
	Underwater.set_lamp(cam.position + Vector3(cs[3], 0, 0), Vector3(0, 0, -1), I)
	wait = 3


func _process(_dt: float) -> void:
	if wait > 0:
		wait -= 1
		if wait == 0:
			_capture()
			_next_case()


func _capture() -> void:
	var img := get_viewport().get_texture().get_image()
	var cs: Array = CASES[case_i]
	var sectors := []
	for q in plate.get_children():
		var P: Vector3 = q.global_position
		var px := cam.unproject_position(P)
		# среднее блока 8×8 в линейном цвете (шейдер дизерит по Байеру 4×4), затем снова sRGB
		var acc := Vector3.ZERO
		for dy in range(-4, 4):
			for dx in range(-4, 4):
				var cc := img.get_pixel(roundi(px.x) + dx, roundi(px.y) + dy).srgb_to_linear()
				acc += Vector3(cc.r, cc.g, cc.b)
		acc /= 64.0
		var c := Color(acc.x, acc.y, acc.z).linear_to_srgb()
		sectors.append({"name": q.name, "pixel": [px.x, px.y], "rgb8": [c.r * 255.0, c.g * 255.0, c.b * 255.0],
				"point": [P.x, P.y, P.z], "normal": [0, 0, 1]})
	results.append({"name": cs[0], "water": cs[1], "distance": cs[2], "base": cs[3], "power": cs[4],
			"depth": cs[5], "ambient": cs[6], "cam": [cam.position.x, cam.position.y, cam.position.z],
			"lamp_pos": [cam.position.x + cs[3], cam.position.y, cam.position.z], "lamp_dir": [0, 0, -1],
			"lamp_i": [uw.lamp_intensity("sdvs5", cs[4]).x if cs[4] > 0 else 0.0,
					uw.lamp_intensity("sdvs5", cs[4]).y if cs[4] > 0 else 0.0,
					uw.lamp_intensity("sdvs5", cs[4]).z if cs[4] > 0 else 0.0],
			"esurf": [uw.esurf.x, uw.esurf.y, uw.esurf.z], "exposure": 0.004, "sectors": sectors})
