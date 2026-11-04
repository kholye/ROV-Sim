class_name LensPass
extends CanvasLayer
## Объектив камеры аппарата: прямоугольник на весь экран со шейдером shaders/lens.gdshader поверх 3D и под
## интерфейсом. Пока активна камера аппарата, проход переводит прямолинейный кадр Godot в проекцию объектива
## DiCam 300 (render/dicam_lens.gd); с другими камерами (сзади, обзорная) проход выключен.
## До версии 1.4 здесь же был «стильный вид» (крупные пиксели, дизеринг, зерно) — убран.

const SHADER := preload("res://shaders/lens.gdshader")

var rect: ColorRect
var lens_on := false


func _ready() -> void:
	layer = 0
	rect = ColorRect.new()
	rect.set_anchors_preset(Control.PRESET_FULL_RECT)
	rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var m := ShaderMaterial.new()
	m.shader = SHADER
	rect.material = m
	rect.visible = false
	add_child(rect)
	get_viewport().size_changed.connect(_apply)


## Включить (камера аппарата активна) / выключить; l — параметры объектива (один раз).
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
	rect.visible = lens_on
	var sz := get_viewport().get_visible_rect().size
	(rect.material as ShaderMaterial).set_shader_parameter("lens_aspect", sz.x / maxf(sz.y, 1.0))


## Материал для своей текстуры (окошко «со стороны»): только усиление gain.
static func material_for(_size: Vector2) -> ShaderMaterial:
	var m := ShaderMaterial.new()
	m.shader = SHADER
	m.set_shader_parameter("from_screen", false)
	return m
