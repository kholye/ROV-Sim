class_name MenuKit
extends RefCounted
## Общее для главного меню и паузы: тема (тёмные плоские кнопки, PT Mono), панель настроек, панель ПИД.

const SCENES := {
	"pool": "res://scenes/pool_rings.tscn",
	"wreck": "res://scenes/wreck.tscn",
	"lab": "res://scenes/lab_pool.tscn",
	"menu": "res://scenes/menu.tscn",
}


const BG := Color("0b0806")
const TEXT := Color("f0e8d8")
const DIM := Color(0.94, 0.91, 0.85, 0.55)
const AMBER := Color("f0c27a")
const MUTED := Color("a39177")
const SOFT := Color("b8aa92")
const F_LOGO := "res://assets/fonts/Unbounded-Variable.ttf"
const F_SANS := "res://assets/fonts/IBMPlexSans-Variable.ttf"
const F_MONO := "res://assets/fonts/IBMPlexMono-Regular.ttf"

static var _fonts := {}


## Шрифт нужной толщины из переменного (Unbounded, IBM Plex Sans); один на путь и толщину.
static func vf(path: String, weight := 400) -> Font:
	var key := "%s:%d" % [path, weight]
	if not _fonts.has(key):
		if path == F_MONO:
			_fonts[key] = load(path)
		else:
			var fv := FontVariation.new()
			fv.base_font = load(path)
			fv.variation_opentype = {TextServerManager.get_primary_interface().name_to_tag("wght"): weight}
			_fonts[key] = fv
	return _fonts[key]


## Тема страниц меню и паузы (стиль главного меню, docs/ui.md): тёмный фон, IBM Plex Sans, янтарный акцент.
static func theme() -> Theme:
	var t := Theme.new()
	t.default_font = vf(F_SANS, 500)
	t.default_font_size = 17
	t.set_color("font_color", "Label", TEXT)
	var normal := _box(Color(0, 0, 0, 0), Color(TEXT, 0.16))
	var hover := _box(Color(AMBER, 0.08), AMBER)
	var pressed := _box(AMBER, AMBER)
	for cls in ["Button", "OptionButton"]:
		t.set_stylebox("normal", cls, normal)
		t.set_stylebox("hover", cls, hover)
		t.set_stylebox("focus", cls, hover)
		t.set_stylebox("pressed", cls, pressed)
		t.set_stylebox("hover_pressed", cls, pressed)
		t.set_color("font_color", cls, TEXT)
		t.set_color("font_hover_color", cls, Color.WHITE)
		t.set_color("font_focus_color", cls, Color.WHITE)
		t.set_color("font_pressed_color", cls, BG)
		t.set_color("font_hover_pressed_color", cls, BG)
	var le := StyleBoxFlat.new()
	le.bg_color = Color(TEXT, 0.04)
	le.border_width_bottom = 1
	le.border_color = Color(TEXT, 0.3)
	le.content_margin_left = 10
	le.content_margin_right = 10
	le.content_margin_top = 6
	le.content_margin_bottom = 6
	var lef := le.duplicate() as StyleBoxFlat
	lef.border_color = AMBER
	t.set_stylebox("normal", "LineEdit", le)
	t.set_stylebox("focus", "LineEdit", lef)
	t.set_color("font_color", "LineEdit", TEXT)
	t.set_color("caret_color", "LineEdit", AMBER)
	for cls in ["CheckBox"]:
		t.set_stylebox("normal", cls, StyleBoxEmpty.new())
		t.set_stylebox("hover", cls, StyleBoxEmpty.new())
		t.set_stylebox("focus", cls, _underline())
		t.set_stylebox("pressed", cls, StyleBoxEmpty.new())
		t.set_stylebox("hover_pressed", cls, StyleBoxEmpty.new())
		t.set_color("font_color", cls, SOFT)
		t.set_color("font_hover_color", cls, Color.WHITE)
		t.set_color("font_focus_color", cls, Color.WHITE)
		t.set_color("font_pressed_color", cls, TEXT)
		t.set_color("font_hover_pressed_color", cls, Color.WHITE)
	t.set_icon("checked", "CheckBox", _check_icon(true))
	t.set_icon("unchecked", "CheckBox", _check_icon(false))
	var pm := StyleBoxFlat.new()
	pm.bg_color = Color("16100a")
	pm.set_border_width_all(1)
	pm.border_color = Color(AMBER, 0.4)
	pm.set_content_margin_all(6)
	t.set_stylebox("panel", "PopupMenu", pm)
	t.set_color("font_color", "PopupMenu", TEXT)
	t.set_color("font_hover_color", "PopupMenu", AMBER)
	var sl := StyleBoxFlat.new()
	sl.bg_color = Color(TEXT, 0.15)
	sl.content_margin_top = 2
	sl.content_margin_bottom = 2
	var sa := sl.duplicate() as StyleBoxFlat
	sa.bg_color = AMBER
	t.set_stylebox("slider", "HSlider", sl)
	t.set_stylebox("grabber_area", "HSlider", sa)
	t.set_stylebox("grabber_area_highlight", "HSlider", sa)
	t.set_color("default_color", "RichTextLabel", SOFT)
	t.set_font("mono_font", "RichTextLabel", vf(F_MONO))
	return t


## Значок галочки 18 × 18: рамка цвета текста, включено — янтарный квадрат внутри.
static func _check_icon(on: bool) -> ImageTexture:
	var n := 18
	var img := Image.create(n, n, false, Image.FORMAT_RGBA8)
	img.fill(Color(0, 0, 0, 0))
	for i in n:
		for e in [0, n - 1]:
			img.set_pixel(i, e, Color(TEXT, 0.5))
			img.set_pixel(e, i, Color(TEXT, 0.5))
	if on:
		img.fill_rect(Rect2i(4, 4, n - 8, n - 8), AMBER)
	return ImageTexture.create_from_image(img)


static func _underline() -> StyleBoxFlat:
	var s := StyleBoxFlat.new()
	s.draw_center = false
	s.border_width_bottom = 1
	s.border_color = AMBER
	return s


static func _box(bg: Color, border: Color) -> StyleBoxFlat:
	var s := StyleBoxFlat.new()
	s.bg_color = bg
	s.set_border_width_all(1)
	s.border_color = border
	s.set_corner_radius_all(4)
	s.content_margin_left = 16
	s.content_margin_right = 16
	s.content_margin_top = 7
	s.content_margin_bottom = 7
	return s


## Панель поверх игры (пауза): тёмная, без рамки.
static func panel(w: float) -> PanelContainer:
	var p := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(BG, 0.96)
	sb.border_width_left = 2
	sb.border_color = Color(AMBER, 0.6)
	sb.set_content_margin_all(28)
	p.add_theme_stylebox_override("panel", sb)
	p.custom_minimum_size = Vector2(w, 0)
	return p


static func button(parent: Node, text: String, cb: Callable) -> Button:
	var b := Button.new()
	b.text = text
	b.alignment = HORIZONTAL_ALIGNMENT_LEFT
	b.pressed.connect(cb)
	parent.add_child(b)
	return b


## Заголовок: крупный — Unbounded (страница, пауза), мелкий (size < 20) — подпись раздела моноширинным.
static func heading(parent: Node, text: String, size := 22) -> Label:
	var l := Label.new()
	l.text = text
	if size >= 20:
		l.add_theme_font_override("font", vf(F_LOGO, 700))
		l.add_theme_font_size_override("font_size", size)
		l.add_theme_color_override("font_color", TEXT)
	else:
		l.add_theme_font_override("font", vf(F_MONO))
		l.add_theme_font_size_override("font_size", 12)
		l.add_theme_color_override("font_color", MUTED)
	parent.add_child(l)
	return l


static func note(parent: Node, text: String) -> Label:
	var l := Label.new()
	l.text = text
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.add_theme_font_override("font", vf(F_SANS, 400))
	l.add_theme_font_size_override("font_size", 15)
	l.add_theme_color_override("font_color", SOFT)
	parent.add_child(l)
	return l


## Настройки (главное меню и пауза): звук, режим управления, графика; сразу сохраняются, on_change — после
## каждого изменения. Остальное (окошко, силы, график, ослабление света, камера) — клавишами в сцене (F1).
static func settings_box(on_change: Callable) -> VBoxContainer:
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 8)
	heading(v, "ЗВУК", 12)
	for item in [["volume", "Общая"], ["volume_music", "Музыка"], ["volume_sfx", "Звуки"]]:
		var row := HBoxContainer.new()
		var l := Label.new()
		l.text = item[1]
		l.custom_minimum_size = Vector2(170, 0)
		row.add_child(l)
		var sl := HSlider.new()
		sl.min_value = 0.0
		sl.max_value = 1.0
		sl.step = 0.05
		sl.value = float(Settings.get_value(item[0]))
		sl.custom_minimum_size = Vector2(300, 24)
		sl.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		var key: String = item[0]
		sl.value_changed.connect(func(val): Settings.set_value(key, val); Settings.apply_global())
		row.add_child(sl)
		v.add_child(row)
	_gap(v)
	heading(v, "УПРАВЛЕНИЕ", 12)
	var rowm := HBoxContainer.new()
	var lm := Label.new()
	lm.text = "Режим"
	lm.custom_minimum_size = Vector2(170, 0)
	rowm.add_child(lm)
	var om := OptionButton.new()
	var keys := Settings.MODES.keys()
	for i in keys.size():
		om.add_item(Settings.MODES[keys[i]], i)
	om.select(maxi(keys.find(String(Settings.get_value("control"))), 0))
	om.item_selected.connect(func(i): Settings.set_value("control", keys[i]); on_change.call())
	rowm.add_child(om)
	v.add_child(rowm)
	note(v, "Научный — как настоящий пульт. Автопилот — та же физика, пульт помогает: плавный ход, держит курс, " +
			"дифферент и глубину (E / Q). Автопилот + ускорение — ещё насос цистерн ×3 и тяга ×1,5. " +
			"Режим действует со следующего запуска сцены; результаты в таблицах — по режимам.")
	_gap(v)
	heading(v, "ГРАФИКА", 12)
	var rowr := HBoxContainer.new()
	var lr := Label.new()
	lr.text = "Разрешение 3D"
	lr.custom_minimum_size = Vector2(170, 0)
	rowr.add_child(lr)
	var orr := OptionButton.new()
	var scales := [1.0, 0.75, 0.5]
	for i in scales.size():
		orr.add_item(["100 % (чётче)", "75 %", "50 % (быстрее)"][i], i)
	var cur := float(Settings.get_value("render_scale"))
	var best := 0
	for i in scales.size():
		if absf(scales[i] - cur) < absf(scales[best] - cur):
			best = i
	orr.select(best)
	orr.item_selected.connect(func(i): Settings.set_value("render_scale", scales[i]); on_change.call())
	rowr.add_child(orr)
	v.add_child(rowr)
	for item in [["vsync", "Вертикальная синхронизация"], ["show_fps", "Показывать кадры в секунду"]]:
		var cb := CheckBox.new()
		cb.text = item[1]
		cb.button_pressed = bool(Settings.get_value(item[0]))
		var key: String = item[0]
		cb.toggled.connect(func(on): Settings.set_value(key, on); Settings.apply_global(); on_change.call())
		v.add_child(cb)
	return v


static func _gap(v: Node, h := 10.0) -> void:
	var g := Control.new()
	g.custom_minimum_size = Vector2(0, h)
	v.add_child(g)


## Панель ПИД, как на пульте: Kp, Kd, Ki числами 0,0-9,9 с шагом 0,1, кнопка «Задать» шлёт команду n.
static func pid_box(rov: Rov) -> VBoxContainer:
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 8)
	heading(v, "ПИД ГЛУБИНЫ (команда n пульта)")
	note(v, "Коэффициенты уходят в аппарат целыми 0-99, то есть 0,0-9,9 с шагом 0,1. По умолчанию " +
			"Kp 0,2 Kd 5,1 Ki 0,0 — подобраны в симуляторе (проверка V3), прошивочные не известны.")
	var g: Array = Settings.get_value("pid")
	var spins := []
	for i in 3:
		var row := HBoxContainer.new()
		var l := Label.new()
		l.text = ["Kp", "Kd", "Ki"][i]
		l.custom_minimum_size = Vector2(60, 0)
		row.add_child(l)
		var s := SpinBox.new()
		s.min_value = 0.0
		s.max_value = 9.9
		s.step = 0.1
		s.value = float(g[i])
		row.add_child(s)
		spins.append(s)
		v.add_child(row)
	var st := Label.new()
	st.add_theme_font_size_override("font_size", 15)
	button(v, "Задать (n)", func():
		var k := [RovControl.quantize_gain(spins[0].value), RovControl.quantize_gain(spins[1].value), RovControl.quantize_gain(spins[2].value)]
		Settings.set_value("pid", k)
		if rov:
			rov.set_pid(k[0], k[1], k[2])
		st.text = "отправлено: Kp %s Kd %s Ki %s" % [Hud.num(k[0], 1), Hud.num(k[1], 1), Hud.num(k[2], 1)])
	v.add_child(st)
	return v
