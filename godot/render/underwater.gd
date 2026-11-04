class_name Underwater
extends RefCounted
## Подводный свет в Godot: читает godot/physics/light_params.json (те же числа, что Python-эталон
## physics_ref/rov/light.py), считает коэффициенты воды сцены и передаёт их в глобальные параметры
## шейдера shaders/underwater.gdshaderinc. Перевод NED -> Godot только через NedGodot.

const PARAMS := "res://physics/light_params.json"
const SURFACE_SHADER := preload("res://shaders/underwater_surface.gdshader")
const VOLUME_SHADER := preload("res://shaders/underwater_volume.gdshader")

var p: Dictionary
var a := Vector3.ZERO     # поглощение, 1/м (R, G, B)
var b := Vector3.ZERO     # рассеяние, 1/м
var c := Vector3.ZERO
var kd := Vector3.ZERO
var esurf := Vector3.ZERO
var bp550 := 0.0          # рассеяние взвесью при 550 нм, 1/м
var turbidity := 1.0      # множитель рассеяния взвесью (мутность у края места, set_turbidity)
var _a_w := Vector3.ZERO  # поглощение и чистая вода без взвеси
var _b_w := Vector3.ZERO
var _b_p := Vector3.ZERO  # рассеяние взвесью воды сцены
var _materials := {}      # исходный материал -> ShaderMaterial


static func load_params(path := PARAMS) -> Dictionary:
	var raw: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
	var out := {}
	for k in raw:
		if not String(k).begins_with("_"):
			out[k] = raw[k]["value"]
	return out


static func v3(arr) -> Vector3:
	return Vector3(arr[0], arr[1], arr[2])


## water: "pool" (бассейн кафедры, подогнано по кадрам Холопова), "wreck" (вода у судна, оценка)
## или "turbid" (кадр murky_1m Холопова).
func _init(water := "pool", e_surface_key := "pool_e_surface") -> void:
	p = load_params()
	var bp: float = p[water + "_bp550"]
	var ax: Vector3 = v3(p[water + "_a_extra_rgb"]) if p.has(water + "_a_extra_rgb") else v3(p["pool_a_extra_rgb"])
	bp550 = bp
	_a_w = v3(p["water_a_rgb"]) + ax
	_b_w = v3(p["water_bw_rgb"])
	_b_p = bp * v3(p["particle_b_shape_rgb"])
	_coeffs()
	esurf = v3(p[e_surface_key])


func _coeffs() -> void:
	a = _a_w
	b = _b_w + turbidity * _b_p
	c = a + b
	kd = (a + float(p["phase_ff_bb"]) * b) / float(p["mean_cosine_down"])


## Мутность у края места (game/tether.gd): рассеяние взвесью × k (k = 1 — вода сцены, поглощение то же).
## Пересчитывает c, b, K_d, глобальные параметры шейдера и модель света аппарата (если передана).
## Игровое оформление границы: облако взвеси вокруг места, оценка; на калибровку воды (V5) не влияет.
func set_turbidity(k: float, light: LightModel = null) -> void:
	turbidity = k
	_coeffs()
	RenderingServer.global_shader_parameter_set("uw_c", c)
	RenderingServer.global_shader_parameter_set("uw_b", b)
	RenderingServer.global_shader_parameter_set("uw_kd", kd)
	if light:
		light.c = c
		light.b = b
		light.kd = kd


## Сила света лампы I0·цвет (кд) при мощности power (0..1), как light.lamp_intensity_I0.
func lamp_intensity(lamp: String, power: float) -> Vector3:
	var I0: float = float(p[lamp + "_flux_50"]) * (power / 0.5) / PI
	return v3(p[lamp + "_rgb"]) * I0


func apply_globals(surface_y := 0.0, exposure := -1.0) -> void:
	var n: float = p["phase_ff_n"]
	var mu: float = p["phase_ff_mu"]
	var nu := (3.0 - mu) / 2.0
	var k := 4.0 / (3.0 * (n - 1.0) * (n - 1.0))
	var kn := pow(k, nu)
	var c180 := (1.0 - kn) / (16.0 * PI * (k - 1.0) * kn)
	RenderingServer.global_shader_parameter_set("uw_c", c)
	RenderingServer.global_shader_parameter_set("uw_b", b)
	RenderingServer.global_shader_parameter_set("uw_kd", kd)
	RenderingServer.global_shader_parameter_set("uw_ff", Vector4(nu, k, c180, float(p["mean_cosine_down"])))
	RenderingServer.global_shader_parameter_set("uw_esurf", esurf)
	RenderingServer.global_shader_parameter_set("uw_surface_y", surface_y)
	RenderingServer.global_shader_parameter_set("uw_exposure", float(p["camera_exposure"]) if exposure < 0 else exposure)
	RenderingServer.global_shader_parameter_set("uw_nlights", 0)
	RenderingServer.global_shader_parameter_set("uw_halo_lut", halo_lut(nu, k, c180))
	RenderingServer.global_shader_parameter_set("uw_caustics", 0.0)
	var ss := silt_star()
	RenderingServer.global_shader_parameter_set("uw_silt_a", ss[0])
	RenderingServer.global_shader_parameter_set("uw_silt_b", ss[1])
	RenderingServer.global_shader_parameter_set("uw_silt_k", ss[2])
	set_silt([])


## Поглощение и рассеяние на массу ила в каналах R, G, B, м²/кг (как silt_star эталона): a*(λ) в центре полосы
## камеры по экспоненте от 443 нм, b* постоянно (physics-sources.md, разд. 29); третье — k = a* + B·b*
## (квазиоднократное приближение, B — доля рассеяния назад).
func silt_star() -> Array:
	var lam: Array = p["camera_band_nm"]
	var a443: float = p["silt_a_star_443"]
	var S: float = p["silt_a_slope"]
	var av := Vector3(a443 * exp(-S * (float(lam[0]) - 443.0)), a443 * exp(-S * (float(lam[1]) - 443.0)),
			a443 * exp(-S * (float(lam[2]) - 443.0)))
	var bs: float = p["silt_b_star"]
	var bv := Vector3(bs, bs, bs)
	return [av, bv, av + float(p["phase_ff_bb"]) * bv]


## Клубы ила для шейдера (не больше 8, SiltPlume.MAX_PUFFS): [{c: центр Godot, m: кг, sh, sv: σ м, bed: высота дна Y}].
## Глобальные параметры uw_spN, uw_ssN (одно общее хранилище, а не массивы в каждом материале).
static func set_silt(puffs: Array) -> void:
	var n := mini(puffs.size(), 8)
	for i in n:
		var f: Dictionary = puffs[i]
		var c: Vector3 = f.c
		RenderingServer.global_shader_parameter_set("uw_sp%d" % i, Vector4(c.x, c.y, c.z, f.m))
		RenderingServer.global_shader_parameter_set("uw_ss%d" % i, Vector4(f.sh, f.sv, f.bed, 0.0))
	if n != _nsilt:
		RenderingServer.global_shader_parameter_set("uw_nsilt", n)
	_nsilt = n


static func set_lamp(pos: Vector3, dir: Vector3, intensity: Vector3) -> void:
	RenderingServer.global_shader_parameter_set("uw_lamp_pos", pos)
	RenderingServer.global_shader_parameter_set("uw_lamp_dir", dir.normalized())
	RenderingServer.global_shader_parameter_set("uw_lamp_i", intensity)


## Таблица F(φ) = ∫ от −π/2 до φ β̃(φ' + π/2) dφ' (256 узлов по φ ∈ [−π/2, π/2]) для ореола источников.
## Интеграл по 8192 шагам со сгущением к φ = −π/2 (там пик рассеяния вперёд, ψ → 0).
static func halo_lut(nu: float, k: float, c180: float) -> ImageTexture:
	var n := 256
	var sub := 32
	var img := Image.create(n, 1, false, Image.FORMAT_RF)
	var acc := 0.0
	var prev_phi := -PI / 2
	img.set_pixel(0, 0, Color(0, 0, 0))
	for i in range(1, n):
		var phi_i := -PI / 2 + PI * i / (n - 1)
		for s in sub:                               # подшаги, квадратично сгущённые к началу отрезка
			var a := prev_phi + (phi_i - prev_phi) * pow(float(s) / sub, 2.0)
			var b := prev_phi + (phi_i - prev_phi) * pow(float(s + 1) / sub, 2.0)
			var psi := (a + b) * 0.5 + PI / 2
			acc += _ff(cos(psi), nu, k, c180) * (b - a)
		img.set_pixel(i, 0, Color(acc, 0, 0))
		prev_phi = phi_i
	return ImageTexture.create_from_image(img)


static func _ff(cos_psi: float, nu: float, k: float, c180: float) -> float:
	var s2 := maxf((1.0 - cos_psi) * 0.5, 1e-6)
	var d := k * s2
	if absf(1.0 - d) < 1e-3:
		d = 1.0 - 1e-3
	var dn := pow(d, nu)
	return (nu * (1.0 - d) - (1.0 - dn) + (d * (1.0 - dn) - nu * (1.0 - d)) / s2) / (4.0 * PI * (1.0 - d) * (1.0 - d) * dn) 			+ c180 * (3.0 * cos_psi * cos_psi - 1.0)


## Неподвижные источники сцены: [{pos: Vector3, i: Vector3 (I0·цвет, кд), dir: Vector3, m: float}], до 16.
## Массивы раздаются всем материалам, созданным здесь (реестр _all), и тем, что будут созданы позже.
static var _all: Array[ShaderMaterial] = []
static var _lp := PackedVector4Array()
static var _li := PackedVector4Array()
static var _ld := PackedVector4Array()
static var _nsilt := -1


static func set_static_lights(lights: Array) -> void:
	var n := mini(lights.size(), 16)
	_lp.resize(16)
	_li.resize(16)
	_ld.resize(16)
	_lp.fill(Vector4.ZERO)
	_li.fill(Vector4.ZERO)
	_ld.fill(Vector4.ZERO)
	for j in n:
		var L: Dictionary = lights[j]
		var d: Vector3 = (L.dir as Vector3).normalized()
		_lp[j] = Vector4(L.pos.x, L.pos.y, L.pos.z, 1.0)
		_li[j] = Vector4(L.i.x, L.i.y, L.i.z, 1.0)
		_ld[j] = Vector4(d.x, d.y, d.z, float(L.m))
	for m in _all:
		_give_lights(m)
	RenderingServer.global_shader_parameter_set("uw_nlights", n)


static func register(m: ShaderMaterial) -> ShaderMaterial:
	_all.append(m)
	_give_lights(m)
	return m


static func _give_lights(m: ShaderMaterial) -> void:
	if _lp.size() == 16:
		m.set_shader_parameter("uw_lp", _lp)
		m.set_shader_parameter("uw_li", _li)
		m.set_shader_parameter("uw_ld", _ld)


static func set_caustics(amp: float) -> void:
	RenderingServer.global_shader_parameter_set("uw_caustics", amp)


static func set_exposure(k: float) -> void:
	RenderingServer.global_shader_parameter_set("uw_exposure", k)


## Материал подводной поверхности. albedo — линейное (не sRGB).
static func material(albedo: Vector3, emission := Vector3.ZERO, tex: Texture2D = null,
		uv_scale := Vector2.ONE) -> ShaderMaterial:
	var m := ShaderMaterial.new()
	m.shader = SURFACE_SHADER
	m.set_shader_parameter("albedo", albedo)
	m.set_shader_parameter("emission", emission)
	m.set_shader_parameter("uv_scale", uv_scale)
	if tex:
		m.set_shader_parameter("albedo_tex", tex)
	return register(m)


## Двусторонний материал водорослей и живности: альбедо × тон цвета вершин, колыхание sway м по альфе.
static func bio(albedo: Vector3, sway: float) -> ShaderMaterial:
	var m := ShaderMaterial.new()
	m.shader = BIO_SHADER
	m.set_shader_parameter("albedo", albedo)
	m.set_shader_parameter("sway", sway)
	return register(m)


static func volume_material() -> ShaderMaterial:
	var m := ShaderMaterial.new()
	m.shader = VOLUME_SHADER
	return register(m)


## Наборы текстур Poly Haven (CC0) в res://assets/textures/<набор>/<набор>_{diff,nor_gl}_1k.jpg.
## Материал Blender «MAT_<набор>[__<второй набор или пометка>]» получает этот набор; масштаб UV и
## поправка альбедо по имени материала (в glTF узел масштаба Blender не попадает).
const TEX_DIR := "res://assets/textures/"
const TEX_SCALE := {"MAT_rust_coarse_01__fine": 3.0, "MAT_green_metal_rust__rust_coarse_01": 1.5}
## Средние линейные альбедо текстур (замер 2026-11-02): ил 0,06, песок 0,21, скан судна 0,12 — как есть;
## сухой камень 0,33 под водой заилен: ×0,5 (оценка).
const TEX_GAIN := {"rock_boulder_dry": 0.5}
## Оттенок по полному имени материала (тот же набор текстур, другой цвет): тёмно-синяя плитка разметки.
const TEX_TINT := {"MAT_pool_tiles__lane": Vector3(0.10, 0.17, 0.45)}
## Сила рельефа (карты нормалей) по имени материала: стены лаб. бассейна по фото автора гладкие (оценка).
const TEX_NORMAL := {"MAT_concrete_wall_006__brown_mud_03": 0.25, "MAT_concrete_wall_006__rust_coarse_01": 0.5}
const TEXTURED_SHADER := preload("res://shaders/underwater_textured.gdshader")
## Водоросли и сидячая живность «BIO_<вид>» (blender/build_wreck_site.py): амплитуда колыхания на конце, м
## (оценка; ламинария гибкая и длинная, актинии лишь шевелят венцом, звёзды и створки неподвижны).
const BIO_SHADER := preload("res://shaders/underwater_bio.gdshader")
const BIO_SWAY := {"BIO_kelp": 0.22, "BIO_redalgae": 0.03, "BIO_metridium": 0.012, "BIO_hydroid": 0.015,
		"BIO_alcyonium": 0.004}


static func tex_set(set_name: String) -> Array:
	var d := TEX_DIR + set_name + "/" + set_name
	if not ResourceLoader.exists(d + "_diff_1k.jpg"):
		return []
	var n: Texture2D = load(d + "_nor_gl_1k.jpg") if ResourceLoader.exists(d + "_nor_gl_1k.jpg") else null
	return [load(d + "_diff_1k.jpg"), n]


static func textured(albedo: Texture2D, normal: Texture2D, uv_scale := 1.0, gain := 1.0) -> ShaderMaterial:
	var m := ShaderMaterial.new()
	m.shader = TEXTURED_SHADER
	m.set_shader_parameter("albedo_tex", albedo)
	if normal:
		m.set_shader_parameter("normal_tex", normal)
		m.set_shader_parameter("has_normal", true)
	m.set_shader_parameter("uv_scale", Vector2(uv_scale, uv_scale))
	m.set_shader_parameter("albedo_gain", Vector3(gain, gain, gain))
	return register(m)


## Материал по имени MAT_<набор>[__<набор2>]: с двумя наборами — смесь по альфе цвета вершин и тон по RGB.
static func textured_from_name(mat_name: String) -> ShaderMaterial:
	if not mat_name.begins_with("MAT_"):
		return null
	var parts := mat_name.substr(4).split("__")
	var a := tex_set(parts[0])
	if a.is_empty():
		return null
	var m := textured(a[0], a[1], float(TEX_SCALE.get(mat_name, 1.0)), float(TEX_GAIN.get(parts[0], 1.0)))
	if TEX_TINT.has(mat_name):
		m.set_shader_parameter("albedo_gain", TEX_TINT[mat_name])
	if TEX_NORMAL.has(mat_name):
		m.set_shader_parameter("normal_strength", TEX_NORMAL[mat_name])
	if parts.size() > 1:
		var b := tex_set(parts[1])
		if not b.is_empty():
			m.set_shader_parameter("albedo_tex2", b[0])
			if b[1]:
				m.set_shader_parameter("normal_tex2", b[1])
			m.set_shader_parameter("use_mix", true)
			m.set_shader_parameter("use_tone", true)
	return m


## Заменяет StandardMaterial3D всех сеток под root на подводные. Цвет glTF уже линейный
## (albedo_color хранится как sRGB-цвет Godot: переводим в линейный). Свечение (LED) переводится
## в яркость emission_cd кд/м².
func convert_tree(root: Node, emission_cd := 2000.0) -> void:
	for n in root.find_children("*", "MeshInstance3D", true, false):
		var mi := n as MeshInstance3D
		for s in mi.mesh.get_surface_count():
			var src := mi.get_active_material(s)
			if src is BaseMaterial3D:
				mi.set_surface_override_material(s, _convert(src))


func _convert(src: BaseMaterial3D) -> ShaderMaterial:
	if _materials.has(src):
		return _materials[src]
	if src.resource_name.begins_with("BIO_"):
		var lc := src.albedo_color.srgb_to_linear()
		_materials[src] = bio(Vector3(lc.r, lc.g, lc.b), float(BIO_SWAY.get(src.resource_name, 0.0)))
		return _materials[src]
	var tm := textured_from_name(src.resource_name)
	if tm == null and src.albedo_texture:          # фото-текстура (скан судна): альбедо как есть
		tm = textured(src.albedo_texture, null)
	if tm:
		_materials[src] = tm
		return tm
	var col := src.albedo_color.srgb_to_linear()
	var em := Vector3.ZERO
	if src.emission_enabled:
		var e: Color = src.emission.srgb_to_linear()
		em = Vector3(e.r, e.g, e.b) * src.emission_energy_multiplier * 500.0
	var m := material(Vector3(col.r, col.g, col.b), em, src.albedo_texture)
	_materials[src] = m
	return m
