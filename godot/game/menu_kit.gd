class_name MenuKit
extends RefCounted
## Общее для главного меню и паузы: тема (тёмные плоские кнопки, PT Mono), панель настроек, панель ПИД.

const SCENES := {
	"pool": "res://scenes/pool_rings.tscn",
	"wreck": "res://scenes/wreck.tscn",
	"lab": "res://scenes/lab_pool.tscn",
	"menu": "res://scenes/menu.tscn",
}


static func theme() -> Theme:
	var t := Hud.make_theme(20)
	var normal := _box(Color(0.06, 0.07, 0.07, 0.9), Color(Hud.WHITE, 0.25))
	var hover := _box(Color(0.14, 0.12, 0.08, 0.95), Hud.AMBER)
	var pressed := _box(Hud.AMBER, Hud.AMBER)
	for cls in ["Button", "OptionButton"]:
		t.set_stylebox("normal", cls, normal)
		t.set_stylebox("hover", cls, hover)
		t.set_stylebox("focus", cls, hover)
		t.set_stylebox("pressed", cls, pressed)
		t.set_color("font_color", cls, Hud.WHITE)
		t.set_color("font_hover_color", cls, Hud.AMBER)
		t.set_color("font_focus_color", cls, Hud.AMBER)
		t.set_color("font_pressed_color", cls, Color.BLACK)
	t.set_stylebox("normal", "LineEdit", normal)
	t.set_stylebox("focus", "LineEdit", hover)
	t.set_color("font_color", "LineEdit", Hud.WHITE)
	t.set_constant("outline_size", "Label", 0)
	t.set_color("font_color", "CheckBox", Hud.WHITE)
	t.set_color("font_hover_color", "CheckBox", Hud.AMBER)
	return t


static func _box(bg: Color, border: Color) -> StyleBoxFlat:
	var s := StyleBoxFlat.new()
	s.bg_color = bg
	s.set_border_width_all(1)
	s.border_color = border
	s.content_margin_left = 16
	s.content_margin_right = 16
	s.content_margin_top = 6
	s.content_margin_bottom = 6
	return s


static func panel(w: float) -> PanelContainer:
	var p := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.02, 0.03, 0.03, 0.9)
	sb.set_border_width_all(1)
	sb.border_color = Color(Hud.WHITE, 0.3)
	sb.set_content_margin_all(24)
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


static func heading(parent: Node, text: String, size := 22) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", Hud.AMBER)
	parent.add_child(l)
	return l


static func note(parent: Node, text: String) -> Label:
	var l := Label.new()
	l.text = text
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.add_theme_font_size_override("font_size", 15)
	l.add_theme_color_override("font_color", Color(Hud.WHITE, 0.7))
	parent.add_child(l)
	return l


## Настройки вида: сразу сохраняются; on_change вызывается после каждого изменения.
static func settings_box(on_change: Callable) -> VBoxContainer:
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 8)
	heading(v, "НАСТРОЙКИ")
	for item in [["filters", "Стильный вид (Tab): крупные пиксели, дизеринг, зерно, виньетка"],
			["pip", "Окошко «со стороны» (V)"], ["forces", "Силы в окошке (F3)"], ["graph", "График глубины (F2)"],
			["light_curve", "Ослабление света (F4)"], ["vsync", "Вертикальная синхронизация"], ["show_fps", "Показывать кадры в секунду"]]:
		var cb := CheckBox.new()
		cb.text = item[1]
		cb.button_pressed = bool(Settings.get_value(item[0]))
		var key: String = item[0]
		cb.toggled.connect(func(on): Settings.set_value(key, on); Settings.apply_global(); on_change.call())
		v.add_child(cb)
	var rowm := HBoxContainer.new()
	var lm := Label.new()
	lm.text = "Режим управления  "
	rowm.add_child(lm)
	var om := OptionButton.new()
	var keys := Settings.MODES.keys()
	for i in keys.size():
		om.add_item(Settings.MODES[keys[i]], i)
	om.select(maxi(keys.find(String(Settings.get_value("control"))), 0))
	om.item_selected.connect(func(i): Settings.set_value("control", keys[i]); on_change.call())
	rowm.add_child(om)
	v.add_child(rowm)
	note(v, "Научный — как настоящий пульт. Автопилот — та же физика, пульт помогает: плавный ход, поворот с постоянной скоростью, держит курс и\n" +
			"дифферент, глубина клавишами E / Q через удержание. Автопилот + ускорение — ещё насос цистерн ×3 и тяга ×1,5.\n" +
			"Режим применяется со следующего запуска уровня; результаты в таблицах — отдельно по режимам.")
	var row := HBoxContainer.new()
	var l := Label.new()
	l.text = "Разрешение 3D в стильном виде  "
	row.add_child(l)
	var ob := OptionButton.new()
	ob.add_item("1/2 (чётче)", 2)
	ob.add_item("1/3 (быстрее)", 3)
	ob.select(0 if int(Settings.get_value("style_scale")) == 2 else 1)
	ob.item_selected.connect(func(i): Settings.set_value("style_scale", ob.get_item_id(i)); on_change.call())
	row.add_child(ob)
	v.add_child(row)
	var row2 := HBoxContainer.new()
	var l2 := Label.new()
	l2.text = "Громкость  "
	row2.add_child(l2)
	var sl := HSlider.new()
	sl.min_value = 0.0
	sl.max_value = 1.0
	sl.step = 0.05
	sl.value = float(Settings.get_value("volume"))
	sl.custom_minimum_size = Vector2(260, 24)
	sl.value_changed.connect(func(val): Settings.set_value("volume", val); Settings.apply_global())
	row2.add_child(sl)
	v.add_child(row2)
	return v


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
