class_name PipView
extends Control
## Окошко «со стороны» (V): вторая камера в том же мире смотрит на аппарат сбоку / сзади / сверху
## (Shift+V), поверх по F3 — векторы сил из физики (RovDynamics.forces): Архимед в ЦВ, вес в ЦМ,
## тяга каждого движителя, сопротивление с плоскостями. Длина стрелки ∝ √F (иначе тяга 1-15 Н не видна
## рядом с весом 80 Н), числа подписаны. Камера следует только за курсом, поэтому дифферент и крен видны.
## Стильный вид: окошко считается в 1/3 разрешения и проходит тот же стиль.
## Экспозиция общая с камерой аппарата (глобальный параметр шейдера), поэтому окошко получает своё
## усиление по замеру той же моделью света (Rov.metered_luminance): ×1-16, подписано на окошке.

const CAMS := ["ВИД СБОКУ", "ВИД СЗАДИ", "ВИД СВЕРХУ"]
const ARROW_K := 0.05            # м на √Н: 80 Н -> 0,45 м, 10 Н -> 0,16 м
const SIZE := Vector2(440, 248)

var rov: Rov
var cam_mode := 0
var show_forces := true
var styled := true
var vp: SubViewport
var cam: Camera3D
var tex: TextureRect
var overlay: Control
var gain := 1.0
var _font: Font
var _mat: ShaderMaterial
var _meter_n := 0


func setup(r: Rov) -> void:
	rov = r
	size = SIZE
	custom_minimum_size = SIZE
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	vp = SubViewport.new()
	vp.render_target_update_mode = SubViewport.UPDATE_WHEN_PARENT_VISIBLE
	vp.msaa_3d = Viewport.MSAA_DISABLED
	add_child(vp)
	cam = Camera3D.new()
	cam.fov = 60.0
	cam.near = 0.05
	cam.far = 60.0
	vp.add_child(cam)
	cam.current = true
	# рамка: тонкая белая с чёрной обводкой
	var frame := Panel.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color.BLACK
	sb.set_border_width_all(2)
	sb.border_color = Hud.WHITE
	sb.shadow_color = Color(0, 0, 0, 0.6)
	sb.shadow_size = 8
	frame.add_theme_stylebox_override("panel", sb)
	frame.set_anchors_preset(Control.PRESET_FULL_RECT)
	frame.offset_left = -2
	frame.offset_top = -2
	frame.offset_right = 2
	frame.offset_bottom = 2
	frame.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(frame)
	tex = TextureRect.new()
	tex.texture = vp.get_texture()
	tex.set_anchors_preset(Control.PRESET_FULL_RECT)
	tex.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	tex.stretch_mode = TextureRect.STRETCH_SCALE
	tex.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(tex)
	overlay = Control.new()
	overlay.set_anchors_preset(Control.PRESET_FULL_RECT)
	overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE
	overlay.draw.connect(_draw_overlay)
	add_child(overlay)
	_font = Hud.FONT
	set_styled(styled)


func set_styled(v: bool) -> void:
	styled = v
	if vp == null:
		return
	var n := 3 if v else 1
	vp.size = Vector2i(int(SIZE.x / n), int(SIZE.y / n))
	tex.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST if v else CanvasItem.TEXTURE_FILTER_LINEAR
	_mat = StylePass.material_for(Vector2(vp.size))
	_mat.set_shader_parameter("stylize", v)
	tex.material = _mat


func _process(_dt: float) -> void:
	if rov == null or not is_visible_in_tree():
		return
	_place_camera()
	_meter_n += 1
	if _meter_n % 6 == 1 and rov.light:
		var lum := rov.metered_luminance(cam, Vector2(vp.size), 3)
		var want := clampf(Rov.AE_TARGET / maxf(lum, 1e-6) / maxf(rov.exposure, 1e-6), 1.0, 16.0)
		gain *= pow(want / gain, 0.3)
		_mat.set_shader_parameter("gain", gain)
	overlay.queue_redraw()


## Камера в осях «курс без дифферента и крена» (NED), затем через NedGodot в мир.
func _place_camera() -> void:
	var psi := rov.x[5]
	var off: Array = [[0.0, 1.7, -0.15], [-1.6, 0.0, -0.35], [0.05, 0.0, -2.2]][cam_mode]
	var off_n := PackedFloat64Array([cos(psi) * off[0] - sin(psi) * off[1], sin(psi) * off[0] + cos(psi) * off[1], off[2]])
	var c := rov.global_position
	var want := c + NedGodot.vec(off_n)
	# не заходить за стенки и дно: луч от аппарата к камере
	var q := PhysicsRayQueryParameters3D.create(c, want, 1)
	var hit := rov.get_world_3d().direct_space_state.intersect_ray(q)
	if not hit.is_empty():
		want = (hit["position"] as Vector3) + (c - want).normalized() * 0.08
	var up := Vector3.UP
	if cam_mode == 2:
		up = NedGodot.vec(PackedFloat64Array([cos(psi), sin(psi), 0.0]))   # сверху: нос аппарата вверху окошка
	cam.look_at_from_position(want, c, up)


func _to_px(world: Vector3) -> Vector2:
	return cam.unproject_position(world) * (size / Vector2(vp.size))


func _draw_overlay() -> void:
	var fs := 13
	_label(Vector2(8, 16), "%s · V%s" % [CAMS[cam_mode], ("   усиление ×%d" % roundi(gain)) if gain >= 1.5 else ""], Hud.WHITE, fs)
	if not show_forces or rov == null:
		_label(Vector2(8, size.y - 8), "F3 — силы", Color(Hud.WHITE, 0.7), 12)
		return
	var f: Dictionary = rov.dyn.forces(rov.x, rov.thr, rov.dropped)
	var up := Vector3.UP
	var B: float = f["B"]
	var W: float = f["W"]
	_arrow(rov.to_global(NedGodot.vec(f["rb"])), up, B, Hud.BLUE, "Архимед %.1f Н" % B)
	_arrow(rov.to_global(NedGodot.vec(f["rg"])), -up, W, Hud.ORANGE, "вес %.1f Н" % W)
	var fwd := rov.global_basis * NedGodot.vec(PackedFloat64Array([1, 0, 0]))
	var tp: Array = f["thr_pos"]
	var T: PackedFloat64Array = f["T"]
	for k in 2:
		if absf(T[k]) > 0.05:
			_arrow(rov.to_global(NedGodot.vec(tp[k])), fwd * signf(T[k]), absf(T[k]), Hud.GREEN,
					"%s %.1f Н" % ["Л" if k == 0 else "П", absf(T[k])])
	var d: PackedFloat64Array = f["drag"]
	var dw := rov.global_basis * NedGodot.vec(d)
	if dw.length() > 0.05:
		_arrow(rov.global_position, dw.normalized(), dw.length(), Hud.WHITE, "сопр. %.1f Н" % dw.length())
	_label(Vector2(size.x - 160, 16), "СИЛЫ · F3", Hud.WHITE, fs)
	# плавучесть итог: это она тянет вверх или вниз при пустом ходе
	var net := B - W
	_label(Vector2(8, size.y - 26), "B − W = %+.2f Н (%s)" % [net, "всплывает" if net > 0.02 else ("тонет" if net < -0.02 else "нейтрален")],
			Hud.AMBER, 12)
	_label(Vector2(8, size.y - 8), "дифферент %+.1f°  крен %+.1f°  длина ∝ √F" % [rad_to_deg(rov.x[4]), rad_to_deg(rov.x[3])],
			Hud.WHITE, 12)


func _arrow(at: Vector3, dir: Vector3, F: float, col: Color, text: String) -> void:
	var a := _to_px(at)
	var b := _to_px(at + dir.normalized() * ARROW_K * sqrt(F))
	if cam.is_position_behind(at):
		return
	var v := b - a
	if v.length() < 3.0:
		return
	var n := v.normalized()
	var h1 := b - n * 9.0 + n.orthogonal() * 5.0
	var h2 := b - n * 9.0 - n.orthogonal() * 5.0
	for pass_i in 2:
		var c := Color.BLACK if pass_i == 0 else col
		var w := 5.0 if pass_i == 0 else 2.5
		overlay.draw_line(a, b - n * 4.0, c, w, true)
		overlay.draw_colored_polygon(PackedVector2Array([b, h1, h2]), c)
		if pass_i == 0:
			overlay.draw_polyline(PackedVector2Array([b, h1, h2, b]), c, 2.0, true)
	overlay.draw_circle(a, 3.5, col)
	_label(b + n * 6.0 + Vector2(4, 4), text, col, 12)


func _label(p: Vector2, t: String, col: Color, fs: int) -> void:
	p.x = clampf(p.x, 4.0, size.x - 4.0 - _font.get_string_size(t, HORIZONTAL_ALIGNMENT_LEFT, -1, fs).x)
	p.y = clampf(p.y, fs + 2.0, size.y - 4.0)
	overlay.draw_string_outline(_font, p, t, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, 4, Color.BLACK)
	overlay.draw_string(_font, p, t, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, col)
