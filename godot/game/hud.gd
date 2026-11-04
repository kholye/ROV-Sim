class_name Hud
extends CanvasLayer
## Экран оператора, вариант «видеоканал с наложением» (docs/ui.md): цифры поверх камеры, как видеоканал
## настоящего ТНПА. Лента курса сверху, шкала глубины справа с меткой цели, режим и ПИД слева вверху,
## задание справа вверху, цистерны и движители слева внизу, батарея, лампа и груз справа внизу.
## Окошко «со стороны» слева вверху (V), научный слой: F2 график глубины,
## F3 силы в окошке, F4 ослабление света. F1 — справка. Числа берутся из модели аппарата (Rov);
## глубина — с шумом датчика, как её видит оператор.

const WHITE := Color(0.95, 0.95, 0.92)
const AMBER := Color(0.91, 0.69, 0.29)
const RED := Color(1.0, 0.36, 0.28)
const BLUE := Color(0.36, 0.72, 0.87)
const GREEN := Color(0.55, 0.85, 0.45)
const ORANGE := Color(0.95, 0.56, 0.32)
const FONT := preload("res://assets/fonts/PTMono-Regular.ttf")

var level: LevelBase
var rov: Rov
var root: Control
var tl: RichTextLabel
var tr: Label
var prompt: Label
var bl: RichTextLabel
var br: RichTextLabel
var att: Label
var compass: Compass
var ladder: Ladder
var cross: Cross
var graph: DepthGraph
var curve: LightCurve
var pip: PipView
var help: Control
var results: ResultsTable
var fps: Label


static func make_theme(size := 18) -> Theme:
	var t := Theme.new()
	t.default_font = FONT
	t.default_font_size = size
	for cls in ["Label", "RichTextLabel"]:
		t.set_color("font_outline_color", cls, Color.BLACK)
		t.set_constant("outline_size", cls, 5)
	t.set_color("font_color", "Label", WHITE)
	t.set_color("default_color", "RichTextLabel", WHITE)
	return t


## Число с запятой, как в русских подписях.
static func num(v: float, digits := 2) -> String:
	v = snappedf(v, pow(10.0, -digits)) + 0.0       # без «−0,00»
	return (("%." + str(digits) + "f") % v).replace(".", ",")


func setup(lvl: LevelBase, r: Rov) -> void:
	level = lvl
	rov = r
	layer = 2
	root = Control.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.theme = make_theme()
	add_child(root)
	tl = _rich(Vector4(0, 0, 0, 0), Vector4(24, 14, 640, 120))
	tr = Label.new()
	_anchor(tr, Vector4(1, 0, 1, 0), Vector4(-520, 14, -24, 140))
	tr.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	root.add_child(tr)
	compass = Compass.new()
	compass.hud = self
	_anchor(compass, Vector4(0.5, 0, 0.5, 0), Vector4(-250, 10, 250, 60))
	root.add_child(compass)
	ladder = Ladder.new()
	ladder.hud = self
	_anchor(ladder, Vector4(1, 0.5, 1, 0.5), Vector4(-160, -190, -40, 190))
	root.add_child(ladder)
	cross = Cross.new()
	_anchor(cross, Vector4(0.5, 0.5, 0.5, 0.5), Vector4(-40, -40, 40, 40))
	root.add_child(cross)
	att = Label.new()
	att.add_theme_font_size_override("font_size", 15)
	att.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_anchor(att, Vector4(0.5, 0.5, 0.5, 0.5), Vector4(-200, 46, 200, 70))
	root.add_child(att)
	prompt = Label.new()
	prompt.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	prompt.add_theme_font_size_override("font_size", 20)
	_anchor(prompt, Vector4(0.5, 0.5, 0.5, 0.5), Vector4(-420, 84, 420, 150))
	root.add_child(prompt)
	bl = _rich(Vector4(0, 1, 0, 1), Vector4(24, -112, 700, -12))
	br = _rich(Vector4(1, 1, 1, 1), Vector4(-560, -112, -24, -12))
	graph = DepthGraph.new()
	graph.hud = self
	_anchor(graph, Vector4(0, 1, 0, 1), Vector4(24, -262, 354, -128))
	root.add_child(graph)
	curve = LightCurve.new()
	curve.hud = self
	_anchor(curve, Vector4(1, 1, 1, 1), Vector4(-520, -262, -190, -128))
	root.add_child(curve)
	pip = PipView.new()
	pip.position = Vector2(24, 112)
	root.add_child(pip)
	pip.setup(rov)
	fps = Label.new()
	fps.add_theme_font_size_override("font_size", 13)
	_anchor(fps, Vector4(0.5, 1, 0.5, 1), Vector4(-60, -24, 60, -6))
	fps.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	root.add_child(fps)
	results = ResultsTable.new()
	results.visible = false
	_anchor(results, Vector4(0.5, 0.5, 0.5, 0.5), Vector4(-560, -250, 560, 250))
	root.add_child(results)
	help = _make_help()
	help.visible = false
	root.add_child(help)
	apply_settings()


func apply_settings() -> void:
	pip.visible = bool(Settings.get_value("pip"))
	pip.cam_mode = int(Settings.get_value("pip_cam"))
	pip.show_forces = bool(Settings.get_value("forces"))
	graph.visible = bool(Settings.get_value("graph"))
	curve.visible = bool(Settings.get_value("light_curve"))
	fps.visible = bool(Settings.get_value("show_fps"))


func _anchor(c: Control, a: Vector4, o: Vector4) -> void:
	c.anchor_left = a.x
	c.anchor_top = a.y
	c.anchor_right = a.z
	c.anchor_bottom = a.w
	c.offset_left = o.x
	c.offset_top = o.y
	c.offset_right = o.z
	c.offset_bottom = o.w
	c.mouse_filter = Control.MOUSE_FILTER_IGNORE


func _rich(a: Vector4, o: Vector4) -> RichTextLabel:
	var r := RichTextLabel.new()
	r.bbcode_enabled = true
	r.scroll_active = false
	r.fit_content = false
	r.autowrap_mode = TextServer.AUTOWRAP_OFF
	_anchor(r, a, o)
	root.add_child(r)
	return r


## Переключатели интерфейса (не команды пульта). Возвращает true, если событие обработано.
func handle(ev: InputEvent) -> bool:
	if ev.is_action("pip_cam") and Input.is_key_pressed(KEY_SHIFT):
		pip.cam_mode = (pip.cam_mode + 1) % PipView.CAMS.size()
		Settings.set_value("pip_cam", pip.cam_mode)
		pip.visible = true
		Settings.set_value("pip", true)
	elif ev.is_action("pip"):
		pip.visible = Settings.toggle("pip")
	elif ev.is_action("forces"):
		pip.show_forces = Settings.toggle("forces")
		if pip.show_forces and not pip.visible:
			pip.visible = true
			Settings.set_value("pip", true)
	elif ev.is_action("graph"):
		graph.visible = Settings.toggle("graph")
	elif ev.is_action("light_curve"):
		curve.visible = Settings.toggle("light_curve")
	elif ev.is_action("help"):
		help.visible = not help.visible
	else:
		return false
	return true


func _process(_dt: float) -> void:
	if rov == null:
		return
	var x := rov.x
	# слева вверху: запись, режим, ПИД
	var t := ""
	if rov.telemetry.active():
		var s := int(rov.time - rov.telemetry.started_at)
		t += "ПЕТРОВИЧ  [color=#ff5a45]●[/color] ЗАП %02d:%02d:%02d\n" % [s / 3600, s / 60 % 60, s % 60]
	else:
		t += "ПЕТРОВИЧ  [color=#f2f2eab0]F1 справка[/color]\n"
	if rov.emergency:
		t += "[color=#ff5a45]АВАРИЙНОЕ ВСПЛЫТИЕ[/color]\n"
	elif rov.control_mode != "science":
		t += "%s · глубина %s м (E / Q)\n" % [Settings.MODES[rov.control_mode].to_upper(), num(rov.depth_target, 2)]
	elif rov.depth_hold:
		t += "ДЕРЖИМ ГЛУБИНУ %s м · PgUp/PgDn ±%d мм\n" % [num(rov.depth_target, 3), roundi(PultInput.DEPTH_STEPS[rov.step_i] * 1000)]
	else:
		t += "РУЧНОЙ · H удержание глубины\n"
	t += "[font_size=15]ПИД %s / %s / %s   %s[/font_size]" % [num(rov.ctl.kp, 1), num(rov.ctl.kd, 1), num(rov.ctl.ki, 1),
			"КАМЕРА АППАРАТА" if rov.cam_front.current else "ВИД СЗАДИ · C"]
	tl.text = t
	tr.text = level.hud_mission()
	att.text = "ДИФ %s°   КРЕН %s°" % [num(rad_to_deg(x[4]), 1), num(rad_to_deg(x[3]), 1)]
	var msg := level.hud_prompt()
	if rov.time - rov.notice_t < 3.0 and rov.notice != "":
		msg = rov.notice
	prompt.text = msg
	# слева внизу: цистерны (носовая = 1, оценка), движители, скорость
	var cap: float = rov.p["tank_capacity"]
	var b := ""
	for k in 2:
		var v := x[12 + k]
		var n := clampi(roundi(v / cap * 10.0), 0, 10)
		var arrow := "▲" if rov.tank_cmd[k] < 0 else ("▼" if rov.tank_cmd[k] > 0 else " ")
		b += "ЦИСТ %s [color=#5cb8de]%s[/color][color=#f2f2ea60]%s[/color] %2d мл %s\n" % [
			"Н" if k == 0 else "К", "■".repeat(n), "■".repeat(10 - n), roundi(v * 1e6), arrow]
	b += "ДВИЖ Л %+4d  П %+4d   %s м/с" % [roundi(rov.thr[0] * 100), roundi(rov.thr[1] * 100), num(x[6], 2)]
	bl.text = b
	# справа внизу: батарея (напряжение под нагрузкой и время при средней мощности), лампа, груз
	var left := rov.battery_time_left()
	var low := rov.battery.soc() < 0.15
	var r := "[right]%sБАТ %s В  %d:%02d%s\n" % ["[color=#ff5a45]" if low else "", num(rov.battery_voltage(), 1),
			int(left / 3600.0), int(left / 60.0) % 60, "[/color]" if low else ""]
	r += "ЛАМПА %d %%\n" % roundi(rov.lamp_level * 100)
	r += ("[color=#ff5a45]ГРУЗ СБРОШЕН[/color]" if rov.dropped else "ГРУЗ НА МЕСТЕ") + "  ПРОТЕЧКИ НЕТ[/right]"
	br.text = r
	fps.text = "%d к/с" % Engine.get_frames_per_second()
	compass.queue_redraw()
	ladder.queue_redraw()
	if graph.visible:
		graph.sample()
		graph.queue_redraw()
	if curve.visible:
		curve.queue_redraw()


func _make_help() -> Control:
	var p := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.02, 0.03, 0.03, 0.88)
	sb.set_border_width_all(1)
	sb.border_color = Color(WHITE, 0.4)
	sb.set_content_margin_all(22)
	p.add_theme_stylebox_override("panel", sb)
	_anchor(p, Vector4(0.5, 0.5, 0.5, 0.5), Vector4(-560, -300, 560, 300))
	var r := RichTextLabel.new()
	r.bbcode_enabled = true
	r.fit_content = true
	r.scroll_active = false
	r.add_theme_font_size_override("normal_font_size", 16)
	r.text = HELP
	p.add_child(r)
	return p


const HELP := "[color=#e8b04a]УПРАВЛЕНИЕ КАК НА ПУЛЬТЕ[/color]\n[table=3][cell][color=#f2f2ea90]клавиатура[/color][/cell][cell][color=#f2f2ea90]геймпад Xbox[/color][/cell][cell][color=#f2f2ea90]команда в аппарат[/color][/cell][cell]W S A D, ↑ ↓ ← →   [/cell][cell]правый стик   [/cell][cell]ход и поворот: левый = y + x, правый = y − x[/cell][cell]E / Q   [/cell][cell]крестовина ↑/↓ + LT и RT   [/cell][cell]обе цистерны набрать / вытеснить (u / d)[/cell][cell]R / F   [/cell][cell]крестовина ↑/↓ + LT   [/cell][cell]носовая цистерна (дифферент)[/cell][cell]T / G   [/cell][cell]крестовина ↑/↓ + RT   [/cell][cell]кормовая цистерна[/cell][cell]H   [/cell][cell]B   [/cell][cell]удержание глубины вкл/выкл (h, цель в мм)[/cell][cell]PgUp / PgDn   [/cell][cell]Y / A   [/cell][cell]при удержании (H): цель глубины на шаг мельче / глубже — ПИД сам гонит цистерны[/cell][cell][lb] / [rb]   [/cell][cell]крестовина ← / →   [/cell][cell]шаг цели 10 / 50 / 100 / 500 мм[/cell][cell]L   [/cell][cell]LB   [/cell][cell]лампа 0 / 50 / 100 % (L)[/cell][cell]X дважды   [/cell][cell]—   [/cell][cell]сброс груза 1 кг (x, G)[/cell][cell]пробел дважды   [/cell][cell]—   [/cell][cell]аварийное всплытие: цистерны осушаются (A); ещё раз — отмена[/cell][cell]Esc   [/cell][cell]Start   [/cell][cell]пауза: ПИД (n: Kp, Kd, Ki 0,0-9,9), настройки, выход[/cell][/table]\n\n" + \
		"[color=#e8b04a]ЭКРАН[/color]\n" + \
		"I / K · R3 геймпада — наклон камеры аппарата вверх / вниз (0-30°)   V · Back — окошко со стороны   Shift+V — его камера\n" + \
		"F2 — график глубины   F3 — силы в окошке   F4 — ослабление света   C — камера аппарата / вид сзади\n" + \
		"F9 — запись телеметрии в CSV   F12 — снимок с подписью (папка photos)   F1 — эта справка\n\n" + \
		"Крен и боковое смещение у аппарата не управляются (как у настоящего): крен только показывается.\n" + \
		"Режимы автопилот / автопилот + ускорение (настройки): E / Q — глубже / мельче (плавно двигают цель удержания),\n" + \
		"курс и дифферент держатся сами, ход разгоняется плавно."


## Лента курса: 120° на ширину, метки через 5°, подписи через 15°.
class Compass:
	extends Control
	var hud: Hud

	func _draw() -> void:
		var h := hud.rov.heading_deg()
		var w := size.x
		var f := Hud.FONT
		var names := {0: "С", 45: "СВ", 90: "В", 135: "ЮВ", 180: "Ю", 225: "ЮЗ", 270: "З", 315: "СЗ"}
		var a0 := int(ceil((h - 60.0) / 5.0)) * 5
		for a in range(a0, int(h + 60.0) + 1, 5):
			var x := w / 2.0 + (a - h) * w / 120.0
			var dd := posmod(a, 360)
			var big := dd % 15 == 0
			Hud.line(self, Vector2(x, 28), Vector2(x, 14 if big else 20), Hud.WHITE, 2.0 if big else 1.0)
			if big:
				Hud.text(self, Vector2(x, 11), names.get(dd, str(dd)), Hud.WHITE, 12, true)
		draw_colored_polygon(PackedVector2Array([Vector2(w / 2 - 8, 42), Vector2(w / 2, 31), Vector2(w / 2 + 8, 42)]), Hud.AMBER)
		Hud.text(self, Vector2(w / 2 + 14, 44), "%03d°" % posmod(roundi(h), 360), Hud.AMBER, 13, false)


## Шкала глубины: 0,1 м = 20 пикселей, текущая глубина в середине, метка цели при удержании.
class Ladder:
	extends Control
	var hud: Hud

	func _draw() -> void:
		var r := hud.rov
		var d := r.depth_meas
		var mid := size.y / 2.0
		var ppm := 200.0
		var base := roundf(d * 10.0) / 10.0
		for i in range(-10, 11):
			var v := snappedf(base + i * 0.1, 0.1)
			var y := mid + (v - d) * ppm
			if y < 0.0 or y > size.y - 24.0 or v < 0.0:
				continue
			var major := roundi(v * 10.0) % 5 == 0
			Hud.line(self, Vector2(50 if major else 60, y), Vector2(70, y), Hud.WHITE, 2.0)
			if major:
				Hud.text(self, Vector2(44, y + 5), Hud.num(v, 1), Hud.WHITE, 15, false, true)
		if r.depth_hold:
			var ty := clampf(mid + (r.depth_target - d) * ppm, 0.0, size.y - 24.0)
			draw_colored_polygon(PackedVector2Array([Vector2(76, ty), Vector2(90, ty - 7), Vector2(90, ty + 7)]), Hud.AMBER)
		draw_rect(Rect2(74, mid - 12, 52, 24), Color(0, 0, 0, 0.6))
		draw_rect(Rect2(74, mid - 12, 52, 24), Hud.WHITE, false, 1.0)
		Hud.text(self, Vector2(100, mid + 6), Hud.num(d, 2), Hud.WHITE, 15, true)
		Hud.text(self, Vector2(60, size.y - 4), "ГЛУБ, м", Hud.WHITE, 13, true)


class Cross:
	extends Control

	func _draw() -> void:
		for seg in [[Vector2(0, 40), Vector2(26, 40)], [Vector2(54, 40), Vector2(80, 40)], [Vector2(40, 30), Vector2(40, 50)]]:
			Hud.line(self, seg[0], seg[1], Hud.WHITE, 2.0)


## Глубина (датчик) и цель за 60 с, 10 точек в секунду.
class DepthGraph:
	extends Control
	var hud: Hud
	var t: PackedFloat64Array = []
	var d: PackedFloat64Array = []
	var g: PackedFloat64Array = []

	func sample() -> void:
		var r := hud.rov
		if not t.is_empty() and r.time - t[t.size() - 1] < 0.1:
			return
		t.append(r.time)
		d.append(r.depth_meas)
		g.append(r.depth_target if r.depth_hold else NAN)
		while t.size() > 0 and r.time - t[0] > 60.0:
			t.remove_at(0)
			d.remove_at(0)
			g.remove_at(0)

	func _draw() -> void:
		draw_rect(Rect2(Vector2.ZERO, size), Color(0, 0, 0, 0.45))
		draw_rect(Rect2(Vector2.ZERO, size), Color(Hud.WHITE, 0.35), false, 1.0)
		Hud.text(self, Vector2(8, 16), "глубина / цель за 60 с · F2", Hud.WHITE, 12, false)
		if t.size() < 2:
			return
		var lo := INF
		var hi := -INF
		for i in d.size():
			lo = minf(lo, d[i])
			hi = maxf(hi, d[i])
			if not is_nan(g[i]):
				lo = minf(lo, g[i])
				hi = maxf(hi, g[i])
		var c := (lo + hi) / 2.0
		var half := maxf((hi - lo) / 2.0 * 1.15, 0.1)
		var area := Rect2(8, 24, size.x - 16, size.y - 32)
		var t1 := t[t.size() - 1]
		var pts := PackedVector2Array()
		var gp := PackedVector2Array()
		for i in t.size():
			var px := area.position.x + (t[i] - (t1 - 60.0)) / 60.0 * area.size.x
			pts.append(Vector2(px, area.position.y + (d[i] - (c - half)) / (2.0 * half) * area.size.y))
			if not is_nan(g[i]):
				gp.append(Vector2(px, area.position.y + (g[i] - (c - half)) / (2.0 * half) * area.size.y))
		if gp.size() > 1:
			draw_polyline(gp, Hud.AMBER, 1.5)
		draw_polyline(pts, Hud.GREEN, 2.0, true)
		Hud.text(self, Vector2(size.x - 8, 16), "%s…%s м" % [Hud.num(c - half, 2), Hud.num(c + half, 2)], Hud.WHITE, 12, false, true)


## Ослабление прямого света в воде сцены exp(−c·d) по R, G, B (c = a + b из модели света) и
## расстояние до того, что в центре кадра (луч от камеры).
class LightCurve:
	extends Control
	var hud: Hud

	func _draw() -> void:
		draw_rect(Rect2(Vector2.ZERO, size), Color(0, 0, 0, 0.45))
		draw_rect(Rect2(Vector2.ZERO, size), Color(Hud.WHITE, 0.35), false, 1.0)
		var c: Vector3 = hud.level.uw.c
		var dmax := clampf(4.0 / c.y, 3.0, 30.0)
		Hud.text(self, Vector2(8, 16), "свет: доля после пути d · F4", Hud.WHITE, 12, false)
		var area := Rect2(8, 24, size.x - 16, size.y - 44)
		var cols := [Color(1.0, 0.35, 0.3), Color(0.45, 0.9, 0.4), Color(0.4, 0.6, 1.0)]
		for k in 3:
			var pts := PackedVector2Array()
			for i in 61:
				var dd := dmax * i / 60.0
				pts.append(area.position + Vector2(area.size.x * i / 60.0, area.size.y * (1.0 - exp(-c[k] * dd))))
			draw_polyline(pts, cols[k], 2.0, true)
		var cam := hud.get_viewport().get_camera_3d()
		var q := PhysicsRayQueryParameters3D.create(cam.global_position, cam.global_position - cam.global_basis.z * dmax, 1)
		var hit := hud.rov.get_world_3d().direct_space_state.intersect_ray(q)
		if not hit.is_empty():
			var dist := cam.global_position.distance_to(hit["position"])
			var x := area.position.x + dist / dmax * area.size.x
			draw_line(Vector2(x, area.position.y), Vector2(x, area.end.y), Hud.AMBER, 1.0)
			Hud.text(self, Vector2(x + 4, area.position.y + 12), "до цели %s м" % Hud.num(dist, 1), Hud.AMBER, 12, false)
		Hud.text(self, Vector2(8, size.y - 6), "c = %s / %s / %s 1/м   0…%d м" % [Hud.num(c.x, 2), Hud.num(c.y, 2), Hud.num(c.z, 2),
				roundi(dmax)], Hud.WHITE, 12, false)


static func line(ci: CanvasItem, a: Vector2, b: Vector2, col: Color, w: float) -> void:
	ci.draw_line(a, b, Color(0, 0, 0, 0.6), w + 2.0)
	ci.draw_line(a, b, col, w)


static func text(ci: CanvasItem, p: Vector2, s: String, col: Color, fs: int, centered: bool, right := false) -> void:
	var w := FONT.get_string_size(s, HORIZONTAL_ALIGNMENT_LEFT, -1, fs).x
	if centered:
		p.x -= w / 2.0
	elif right:
		p.x -= w
	ci.draw_string_outline(FONT, p, s, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, 4, Color.BLACK)
	ci.draw_string(FONT, p, s, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, col)
