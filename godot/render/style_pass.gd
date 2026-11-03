class_name StylePass
extends CanvasLayer
## Стильный вид (Tab): прямоугольник на весь экран со шейдером shaders/style.gdshader поверх 3D и под
## интерфейсом. Пока стиль включён, 3D считается в 1/N разрешения (Settings «style_scale»): стиль всё
## равно сводит кадр к крупным пикселям, а слабой видеокарте так легче. Научный вид: полное разрешение,
## стиля нет, на экране только расчёт света и интерфейс. С камерой аппарата тот же проход переводит кадр в
## проекцию объектива DiCam 300 (set_lens) — в обоих видах.

const SHADER := preload("res://shaders/style.gdshader")

var rect: ColorRect
var on := true
var lens_on := false           # кадр камеры аппарата через объектив DiCam 300 (render/dicam_lens.gd)


func _ready() -> void:
	layer = 0
	rect = ColorRect.new()
	rect.set_anchors_preset(Control.PRESET_FULL_RECT)
	rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var m := ShaderMaterial.new()
	m.shader = SHADER
	rect.material = m
	add_child(rect)
	get_viewport().size_changed.connect(_apply)


func set_on(v: bool) -> void:
	on = v
	_apply()


## Объектив камеры аппарата: включить (камера аппарата активна) / выключить (вид сзади, обзорная камера).
## В научном виде проход тогда только переводит кадр в проекцию объектива, без стиля.
func set_lens(v: bool, l: DicamLens = null) -> void:
	if v == lens_on and l == null:
		return
	lens_on = v
	var m := rect.material as ShaderMaterial
	m.set_shader_parameter("lens", v)
	if l:
		m.set_shader_parameter("lens_half_air", l.half_air)
		m.set_shader_parameter("lens_half_water", l.half_water())
		m.set_shader_parameter("lens_n", l.n)
	_apply()


func _apply() -> void:
	if rect == null:
		return
	rect.visible = on or lens_on
	(rect.material as ShaderMaterial).set_shader_parameter("stylize", on)
	var vp := get_viewport()
	var n := maxi(int(Settings.get_value("style_scale")), 1)
	vp.scaling_3d_mode = Viewport.SCALING_3D_MODE_BILINEAR
	vp.scaling_3d_scale = 1.0 / n if on else 1.0
	var sz := vp.get_visible_rect().size
	(rect.material as ShaderMaterial).set_shader_parameter("low_res", (sz / n).floor())
	(rect.material as ShaderMaterial).set_shader_parameter("lens_aspect", sz.x / maxf(sz.y, 1.0))


## Материал того же стиля для своей текстуры (окошко): сетка своего размера.
static func material_for(size: Vector2) -> ShaderMaterial:
	var m := ShaderMaterial.new()
	m.shader = SHADER
	m.set_shader_parameter("from_screen", false)
	m.set_shader_parameter("low_res", size)
	return m
