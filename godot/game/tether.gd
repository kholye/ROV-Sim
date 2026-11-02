class_name Tether
extends CanvasLayer
## Граница места (оценка, игровое правило; на физику аппарата не влияет — троса в модели нет):
##  - кабель-трос ТНПА длиной LENGTH м идёт от судна обеспечения, стоящего над местом крушения (точка
##    origin на поверхности); за WARN м до предела видео рябит (длинная линия, натяжение — оформление),
##    на пределе «связь потеряна» и предложение начать заново;
##  - вокруг места облако взвеси: дальше TURBID_FROM м от судна рассеяние взвесью растёт до ×TURBID_MAX
##    к TURBID_TO м (видимость с 7 м падает до ≈ 1 м), поэтому края сцены не видно.

const LENGTH := 22.0
const WARN := 3.5
const TURBID_FROM := 14.5      # старт аппарата в 14 м от судна — ещё в обычной воде
const TURBID_TO := 20.5
const TURBID_MAX := 7.0
const SHADER := preload("res://shaders/interference.gdshader")

var level: LevelBase
var origin := Vector3.ZERO
var center := Vector3.ZERO
var noise := 0.0               # сила помех 0..1
var lost := false
var _rect: ColorRect
var _k := 1.0


## origin — точка на поверхности над судном (откуда идёт кабель); center_ — середина места (для мутности).
func setup(lvl: LevelBase, origin_: Vector3, center_: Vector3) -> void:
	level = lvl
	origin = origin_
	center = center_
	layer = 1                  # над 3D и стилем, под экраном оператора
	_rect = ColorRect.new()
	_rect.set_anchors_preset(Control.PRESET_FULL_RECT)
	_rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var m := ShaderMaterial.new()
	m.shader = SHADER
	_rect.material = m
	_rect.visible = false
	add_child(_rect)
	name = "Tether"


func remaining() -> float:
	return LENGTH - level.rov.global_position.distance_to(origin)


func _process(_dt: float) -> void:
	if level.rov == null:
		return
	var cam := level.rov.camera().global_position
	var h := Vector2(cam.x - center.x, cam.z - center.z).length()
	var k := 1.0 + (TURBID_MAX - 1.0) * smoothstep(TURBID_FROM, TURBID_TO, h)
	if absf(k - _k) > 0.005:
		_k = k
		level.uw.set_turbidity(k, level.rov.light)
	noise = clampf((WARN - remaining()) / WARN, 0.0, 1.0)
	_rect.visible = noise > 0.0
	(_rect.material as ShaderMaterial).set_shader_parameter("amount", noise)
	if remaining() <= 0.0 and not lost:
		lost = true
		level.rov.input_enabled = false
		level.pause.link_lost("Кабель на пределе (%d м): связь с аппаратом потеряна, видео нет." % int(LENGTH))
