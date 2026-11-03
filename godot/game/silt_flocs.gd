class_name SiltFlocs
extends GPUParticles3D
## Хлопья ила — видимые частицы облака (частицы на видеокарте, shaders/silt_flocs.gdshader, вид — silt_flocs_draw).
## Мост: каждый шаг облака (game/silt_cloud.gd) передаёт частицам пятна размыва под струями (центр, разброс, толщина
## струи, дно) и сколько хлопьев рождать (кг/с × хлопьев на кг), струи (срез, направление, U0) и течение — всё из той же
## физики (physics/silt_plume.gd), переведённое в Godot только через NedGodot. Числа хлопьев — light_params.json.

const PROCESS := preload("res://shaders/silt_flocs.gdshader")
const DRAW := preload("res://shaders/silt_flocs_draw.gdshader")

var per_kg := 1.0e6
var _pm: ShaderMaterial
var _dm: ShaderMaterial


func setup(uw: Underwater, rp: Dictionary) -> void:
	var lp := uw.p
	per_kg = lp["silt_flocs_per_kg"]
	var pool: Array = lp["silt_flocs_pool"]
	amount = int(pool[0])
	lifetime = float(pool[1])
	explosiveness = 0.0
	randomness = 0.0
	local_coords = false
	fixed_fps = 0
	interpolate = false
	visibility_aabb = AABB(Vector3(-200, -200, -200), Vector3(400, 400, 400))
	_pm = ShaderMaterial.new()
	_pm.shader = PROCESS
	var rr: Array = lp["silt_floc_radius"]
	_pm.set_shader_parameter("r_min", float(rr[0]))
	_pm.set_shader_parameter("r_max", float(rr[1]))
	_pm.set_shader_parameter("ws", float(rp["silt_ws"]))
	_pm.set_shader_parameter("cd_bed", float(rp["silt_cd_bed"]))
	_pm.set_shader_parameter("cd_cur", float(rp["silt_cd_current"]))
	_pm.set_shader_parameter("jet_spread", float(rp["jet_spread"]))
	_pm.set_shader_parameter("jet_core", float(rp["jet_core"]))
	_pm.set_shader_parameter("pool_rate", float(amount) / lifetime)
	_pm.set_shader_parameter("per_kg", per_kg)
	process_material = _pm
	var q := QuadMesh.new()
	q.size = Vector2.ONE
	_dm = ShaderMaterial.new()
	_dm.shader = DRAW
	_dm.set_shader_parameter("albedo_p", float(lp["particle_albedo"]))
	_dm.set_shader_parameter("defocus_px", float(lp["camera_defocus_px"]))
	_dm.set_shader_parameter("debug_show", OS.get_cmdline_user_args().has("--flocs_debug"))
	q.material = Underwater.register(_dm)
	draw_pass_1 = q
	cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	emitting = false
	name = "SiltFlocs"


## Стенки бассейна (Godot): x мин, x макс, z мин, z макс.
func set_box(b: Vector4) -> void:
	_pm.set_shader_parameter("box", b)


## Обновить по физике облака: plume — SiltPlume после шага, js — его струи (NED), cur — течение NED, h — глубина места.
func update(plume: SiltPlume, js: Array, cur: PackedFloat64Array, h: float) -> void:
	for k in 2:
		var e: Array = plume.last[k]
		var mdot: float = e[0]
		var c := NedGodot.vec(e[1])
		_pm.set_shader_parameter("em%d" % k, Vector4(c.x, c.y, c.z, mdot * per_kg))
		_pm.set_shader_parameter("es%d" % k, Vector4(maxf(sqrt(float(e[2]) / 2.0), 0.05), maxf(float(e[3]), 0.05), c.y, 0.0))
		var j = js[k]
		if j == null:
			_pm.set_shader_parameter("jo%d" % k, Vector4.ZERO)
		else:
			var o := NedGodot.vec(j[0])
			var d := NedGodot.vec(j[1])
			_pm.set_shader_parameter("jo%d" % k, Vector4(o.x, o.y, o.z, float(j[2])))
			_pm.set_shader_parameter("jd%d" % k, Vector4(d.x, d.y, d.z, float(j[3])))
	_pm.set_shader_parameter("cur", NedGodot.vec(cur))
	_pm.set_shader_parameter("site_h", h)
	# без ила (нет ни размыва, ни клубов) частицы выключены: пул на видеокарте не считается
	var any := not plume.puffs.is_empty() or float(plume.last[0][0]) > 0.0 or float(plume.last[1][0]) > 0.0
	if any != emitting:
		emitting = any


func _process(_dt: float) -> void:
	_dm.set_shader_parameter("viewport_h", get_viewport().get_visible_rect().size.y)
