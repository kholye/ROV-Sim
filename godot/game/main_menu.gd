extends Control
## Главное меню (вариант C6b, docs/ui.md): слева логотип и список (Погружение / Результаты / Настройки / Авторы /
## Выход), справа неподвижный снимок гидролокатора бокового обзора над местом судна: по нему сверху вниз идёт
## линия обзора, рамки целей вспыхивают, когда она через них проходит. «Погружение» открывает экран D2: аппарат
## (пока один — «Петрович», рядом свободное место) и сцена с кадром из игры. Страницы (результаты, настройки,
## авторы) — панелью поверх, Esc — назад. При первом запуске — заставка с авторами (Credits).
## Снимок и рамки: blender/render_menu_art.py + work/tools/menu_sidescan.py; TARGETS — габариты объектов
## wreck_site.glb в плане (м, центр места; корпус — по видимому контуру на снимке, габарит модели шире).

const SIDESCAN := preload("res://assets/ui/menu_sidescan.jpg")
const LINEART := preload("res://assets/ui/rov_lineart.png")
const F_LOGO := "res://assets/fonts/Unbounded-Variable.ttf"
const F_SANS := "res://assets/fonts/IBMPlexSans-Variable.ttf"
const F_MONO := preload("res://assets/fonts/IBMPlexMono-Regular.ttf")
const BG := Color("0b0806")
const TEXT := Color("f0e8d8")
const DIM := Color(0.94, 0.91, 0.85, 0.55)
const AMBER := Color("f0c27a")
const MUTED := Color("a39177")
const FOOT := Color("6f6252")
const PLATE := 860.0              # px: снимок 30 × 30 м
const PLATE_Y := -70.0            # сдвиг снимка вверх: судно ближе к середине экрана
const SCAN_T := 7.0               # с: проход линии обзора
const SCAN_H := 40.0
const TARGETS := [                # имя, x0, x1, y0, y1 (м)
	["КОРПУС СУДНА · 8 М", -3.66, 1.92, -5.06, 3.49],
	["ЯКОРЬ", 1.94, 3.07, 7.42, 7.99],
	["БОЧКИ", 1.75, 2.86, -4.87, -2.53],
	["КАМНИ", 7.97, 10.63, 0.93, 3.39],
	["КАМНИ", -9.85, -7.43, -5.05, -3.10],
]
const LEVELS := [
	{"id": "pool", "title": "Бассейн с кольцами", "img": preload("res://assets/ui/menu_pool.jpg"),
		"text": "Шесть колец по порядку на время, 12 × 25 × 5 м."},
	{"id": "wreck", "title": "Затонувшее судно", "img": preload("res://assets/ui/menu_wreck.jpg"),
		"text": "Шесть точек осмотра в мутной воде, кабель 22 м."},
	{"id": "lab", "title": "Лабораторный бассейн", "img": preload("res://assets/ui/menu_lab.jpg"),
		"text": "Бассейн кафедры 3,5 × 3,5 × 3 м с мишенью, сверху — зал лаборатории."},
]
const VEHICLES := [               # профили аппаратов; второй — свободное место под следующий аппарат
	{"name": "ПЕТРОВИЧ", "org": "ТНПА кафедры МИСиТ СПбГМТУ, макет для отработки инженерных решений",
		"spec": [["корпус", "Ø140×650"], ["масса", "8,2 кг"], ["движители", "2"], ["цистерны", "2×70 мл"]]},
	{"name": "СВОБОДНО", "org": "место для следующего аппарата: файл параметров и 3D-модель", "empty": true,
		"spec": [["корпус", "—"], ["масса", "—"], ["движители", "—"], ["цистерны", "—"]]},
]
const SPLASH_T := 2.6
const SPLASH_SKIP := 0.6

static var _level_done := false
static var _splash_done := false
static var _scene := 1
static var _veh := 0

var items: Array[Button] = []
var bars: Array[ColorRect] = []
var targets: Array = []           # [Panel, StyleBoxFlat, Label, задержка]
var scan: TextureRect
var foot: Label
var page_layer: Control
var page_title: Label
var page_back: Button
var page_scroll: ScrollContainer
var page: VBoxContainer
var dive: Control
var rows: Array[Button] = []
var row_style: Array[StyleBoxFlat] = []
var veh_name: Label
var veh_org: Label
var veh_idx: Label
var veh_art: TextureRect
var veh_empty: Panel
var veh_spec: Array[Label] = []
var start_btn: Button
var splash: Control
var _splash_t := 0.0
var _t := 0.0


func _ready() -> void:
	var a := OS.get_cmdline_user_args()
	var lv := a.find("--level")                   # --level pool / wreck / lab: сразу в сцену (сборка .exe
	if lv >= 0 and lv + 1 < a.size() and not _level_done:   # не принимает путь сцены); остальные аргументы читает уровень
		_level_done = true
		_go.call_deferred(a[lv + 1])
		return
	Settings.apply_global()
	PultInput.ensure_actions()
	theme = _theme()
	var bg := ColorRect.new()
	bg.color = BG
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(bg)
	_sonar()
	_left()
	page_layer = Control.new()                      # страницы: на весь экран, как «Погружение»
	page_layer.set_anchors_preset(Control.PRESET_FULL_RECT)
	page_layer.visible = false
	page_layer.theme = MenuKit.theme()
	add_child(page_layer)
	var pbg := ColorRect.new()
	pbg.color = BG
	pbg.set_anchors_preset(Control.PRESET_FULL_RECT)
	page_layer.add_child(pbg)
	_dive_screen()
	UiSound.menu_music(true)
	var k := a.find("--shot")                      # --shot <png>: снимок для docs/ (--page dive/results/authors/settings,
	var shot := k >= 0 and k + 1 < a.size()        # --sel 0..2 сцена, --hover 0..4 пункт под курсором, --splash)
	if not _splash_done and (not shot or a.has("--splash")):
		_splash()
	_splash_done = true
	if shot:
		var sel := a.find("--sel")
		if sel >= 0 and sel + 1 < a.size():
			_scene = int(a[sel + 1])
		var pg := a.find("--page")
		if pg >= 0 and pg + 1 < a.size():
			{"dive": _open_dive, "results": _results.bind(true), "authors": _authors, "settings": _settings,
					"about": _about}.get(a[pg + 1], func(): pass).call()
		var hv := a.find("--hover")
		if hv >= 0 and hv + 1 < a.size():
			items[int(a[hv + 1])].grab_focus()
		var st := a.find("--shot_t")                 # --shot_t с: момент снимка (линия обзора, вспышки)
		var wait := float(a[st + 1]) if st >= 0 and st + 1 < a.size() else 0.5
		await get_tree().create_timer(wait).timeout
		await RenderingServer.frame_post_draw
		get_viewport().get_texture().get_image().save_png(a[k + 1])
		get_tree().quit()


static func _vf(path: String, weight: int) -> FontVariation:
	var fv := FontVariation.new()
	fv.base_font = load(path)
	fv.variation_opentype = {TextServerManager.get_primary_interface().name_to_tag("wght"): weight}
	return fv


func _theme() -> Theme:
	var t := Theme.new()
	t.default_font = _vf(F_SANS, 500)
	t.default_font_size = 18
	var empty := StyleBoxEmpty.new()
	for st in ["normal", "hover", "pressed", "focus", "disabled", "hover_pressed"]:
		t.set_stylebox(st, "Button", empty)
	t.set_color("font_color", "Button", DIM)
	for c in ["font_hover_color", "font_focus_color", "font_pressed_color", "font_hover_pressed_color"]:
		t.set_color(c, "Button", Color.WHITE)
	return t


func _label(text: String, size: int, font: Font, color: Color) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_override("font", font)
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)
	return l


func _grad(colors: Array, horizontal: bool, radial := false) -> GradientTexture2D:
	var g := Gradient.new()
	g.set_color(0, colors[0])
	g.set_color(1, colors[1])
	var gt := GradientTexture2D.new()
	gt.gradient = g
	if radial:
		gt.fill = GradientTexture2D.FILL_RADIAL
		gt.fill_from = Vector2(0.5, 0.45)
		gt.fill_to = Vector2(1.1, 0.45)
	else:
		gt.fill_from = Vector2.ZERO
		gt.fill_to = Vector2(1, 0) if horizontal else Vector2(0, 1)
	return gt


## Справа: неподвижный снимок бокового обзора, линия обзора, рамки целей.
func _sonar() -> void:
	var box := Control.new()
	box.anchor_left = 1.0
	box.anchor_right = 1.0
	box.anchor_bottom = 1.0
	box.offset_left = -PLATE
	box.clip_contents = true
	box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(box)
	var plate := Control.new()
	plate.position = Vector2(0, PLATE_Y)
	plate.size = Vector2(PLATE, PLATE)
	plate.mouse_filter = Control.MOUSE_FILTER_IGNORE
	box.add_child(plate)
	var img := TextureRect.new()
	img.texture = SIDESCAN
	img.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	img.size = Vector2(PLATE, PLATE)
	img.modulate = Color(0.85, 0.85, 0.85)
	plate.add_child(img)
	scan = TextureRect.new()
	scan.texture = _grad([Color(1, 0.89, 0.63, 0), Color(1, 0.94, 0.78, 0.9)], false)
	scan.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	scan.size = Vector2(PLATE, SCAN_H)
	plate.add_child(scan)
	var k := PLATE / 30.0
	var pad := 6.0
	for tg in TARGETS:
		var top := (15.0 - float(tg[4])) * k - pad
		var p := Panel.new()
		p.position = Vector2((float(tg[1]) + 15.0) * k - pad, top)
		p.size = Vector2((float(tg[2]) - float(tg[1])) * k + 2 * pad, (float(tg[4]) - float(tg[3])) * k + 2 * pad)
		p.mouse_filter = Control.MOUSE_FILTER_IGNORE
		var sb := StyleBoxFlat.new()
		sb.draw_center = false
		sb.set_border_width_all(2)
		sb.border_color = Color(1, 1, 1, 0.35)
		sb.shadow_color = Color(1, 0.86, 0.59, 0.0)
		p.add_theme_stylebox_override("panel", sb)
		plate.add_child(p)
		var l := _label(String(tg[0]), 11, F_MONO, Color("140d06"))
		var lb := StyleBoxFlat.new()
		lb.bg_color = Color(1, 1, 1, 0.9)
		lb.content_margin_left = 6
		lb.content_margin_right = 6
		l.add_theme_stylebox_override("normal", lb)
		l.position = Vector2(p.position.x - 1, top - 22)
		plate.add_child(l)
		targets.append([p, sb, l, (top + SCAN_H) / (PLATE + SCAN_H) * SCAN_T])
	var fade := TextureRect.new()
	fade.texture = _grad([BG, Color(BG, 0)], true)
	fade.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	fade.anchor_bottom = 1.0
	fade.offset_right = 120
	fade.mouse_filter = Control.MOUSE_FILTER_IGNORE
	box.add_child(fade)


## Слева: логотип, список, версия и пилот.
func _left() -> void:
	var logo := _label("ROV-SIM", 52, _vf(F_LOGO, 700), TEXT)
	logo.position = Vector2(80, 74)
	add_child(logo)
	var sub := _label("СИМУЛЯТОР ПОДВОДНОГО АППАРАТА", 12, F_MONO, MUTED)
	sub.add_theme_constant_override("line_spacing", 0)
	sub.position = Vector2(82, 150)
	add_child(sub)
	var list := VBoxContainer.new()
	list.position = Vector2(80, 262)
	list.add_theme_constant_override("separation", 0)
	add_child(list)
	var entries := [["ПОГРУЖЕНИЕ", _open_dive], ["РЕЗУЛЬТАТЫ", _results.bind(true)], ["НАСТРОЙКИ", _settings],
			["АВТОРЫ", _authors], ["ВЫХОД", func(): get_tree().quit()]]
	for i in entries.size():
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 16)
		var bar := ColorRect.new()
		bar.color = AMBER
		bar.custom_minimum_size = Vector2(0, 2)
		bar.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		row.add_child(bar)
		var col := VBoxContainer.new()
		col.add_theme_constant_override("separation", -4)
		var b := Button.new()
		b.text = entries[i][0]
		b.alignment = HORIZONTAL_ALIGNMENT_LEFT
		b.add_theme_font_override("font", _vf(F_SANS, 600 if i == 0 else 500))
		b.add_theme_font_size_override("font_size", 34 if i == 0 else 22)
		b.add_theme_constant_override("h_separation", 0)
		if i == 0:                                 # главный пункт заметнее размером, но не «выбран»
			b.add_theme_color_override("font_color", Color(0.94, 0.91, 0.85, 0.82))
		b.pressed.connect(entries[i][1])
		b.mouse_entered.connect(b.grab_focus)
		b.focus_entered.connect(_bar.bind(bar, true))
		b.focus_exited.connect(_bar.bind(bar, false))
		col.add_child(b)
		if i == 0:
			var s := _label("выбор сцены и аппарата", 11, F_MONO, MUTED)
			col.add_child(s)
			col.add_theme_constant_override("separation", -2)
		row.add_child(col)
		list.add_child(row)
		if i == 0:
			var gap := Control.new()
			gap.custom_minimum_size = Vector2(0, 14)
			list.add_child(gap)
		items.append(b)
		bars.append(bar)
	foot = _label("", 12, F_MONO, FOOT)
	foot.anchor_top = 1.0
	foot.anchor_bottom = 1.0
	foot.offset_left = 80
	foot.offset_top = -44
	add_child(foot)
	_update_foot()


func _update_foot() -> void:
	foot.text = "%s · пилот: %s" % [str(ProjectSettings.get_setting("application/config/version", "")), Settings.get_value("player")]


func _bar(bar: ColorRect, on: bool) -> void:
	create_tween().tween_property(bar, "custom_minimum_size:x", 28.0 if on else 0.0, 0.25)


func _process(dt: float) -> void:
	_t += dt
	if splash:
		_splash_t += dt
		if _splash_t > SPLASH_T:
			_end_splash()
	if scan == null:
		return
	scan.position.y = -SCAN_H + fposmod(_t, SCAN_T) / SCAN_T * (PLATE + SCAN_H)
	for tg in targets:                              # вспышка, когда линия доходит до верха рамки, затем гаснет
		var d := fposmod(_t - float(tg[3]), SCAN_T)
		var a := 0.35
		var glow := 0.0
		if d < 0.21:
			a = lerpf(0.35, 1.0, d / 0.21)
			glow = d / 0.21
		elif d < 2.1:
			a = lerpf(1.0, 0.6, (d - 0.21) / 1.89)
			glow = 1.0 - (d - 0.21) / 0.6 if d < 0.81 else 0.0
		else:
			a = lerpf(0.6, 0.35, (d - 2.1) / (SCAN_T - 2.1))
		var sb: StyleBoxFlat = tg[1]
		sb.border_color = Color(1, 1, 1, a)
		sb.shadow_size = int(16.0 * glow)
		sb.shadow_color = Color(1, 0.86, 0.59, 0.7 * glow)
		(tg[2] as Label).modulate.a = clampf(0.45 + 0.55 * (a - 0.35) / 0.65, 0.45, 1.0)


## Экран «Погружение» (D2): слева аппарат, справа сцены с кадрами из игры.
func _dive_screen() -> void:
	dive = Control.new()
	dive.set_anchors_preset(Control.PRESET_FULL_RECT)
	dive.visible = false
	add_child(dive)
	var bg := ColorRect.new()
	bg.color = BG
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	dive.add_child(bg)
	var lp := Control.new()
	lp.anchor_bottom = 1.0
	lp.offset_right = 600
	dive.add_child(lp)
	var glow := TextureRect.new()
	glow.texture = _grad([Color("1c140c"), BG], false, true)
	glow.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	glow.set_anchors_preset(Control.PRESET_FULL_RECT)
	lp.add_child(glow)
	var edge := ColorRect.new()
	edge.color = Color(TEXT, 0.1)
	edge.anchor_left = 1.0
	edge.anchor_right = 1.0
	edge.anchor_bottom = 1.0
	edge.offset_left = -1
	lp.add_child(edge)
	veh_idx = _label("", 11, F_MONO, MUTED)
	veh_idx.position = Vector2(56, 44)
	lp.add_child(veh_idx)
	veh_art = TextureRect.new()
	veh_art.texture = LINEART
	veh_art.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	veh_art.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	veh_art.position = Vector2(40, 110)
	veh_art.size = Vector2(520, 290)
	veh_art.modulate = Color(1.0, 0.86, 0.66)
	lp.add_child(veh_art)
	veh_empty = Panel.new()
	var es := StyleBoxFlat.new()
	es.draw_center = false
	es.set_border_width_all(1)
	es.border_color = Color(TEXT, 0.25)
	es.set_corner_radius_all(10)
	veh_empty.add_theme_stylebox_override("panel", es)
	veh_empty.position = Vector2(100, 130)
	veh_empty.size = Vector2(400, 240)
	lp.add_child(veh_empty)
	var el := _label("Здесь появится другой аппарат:\nфайл параметров и 3D-модель", 15, _vf(F_SANS, 400), MUTED)
	el.set_anchors_preset(Control.PRESET_FULL_RECT)
	el.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	el.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	veh_empty.add_child(el)
	var nrow := HBoxContainer.new()
	nrow.position = Vector2(56, 424)
	nrow.add_theme_constant_override("separation", 16)
	lp.add_child(nrow)
	nrow.add_child(_arrow("‹", -1))
	veh_name = _label("", 34, _vf(F_LOGO, 700), TEXT)
	nrow.add_child(veh_name)
	nrow.add_child(_arrow("›", 1))
	veh_org = _label("", 14, _vf(F_SANS, 400), Color("b8aa92"))
	veh_org.position = Vector2(56, 494)
	veh_org.size = Vector2(500, 40)
	veh_org.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	lp.add_child(veh_org)
	var grid := GridContainer.new()
	grid.columns = 4
	grid.position = Vector2(56, 556)
	grid.add_theme_constant_override("h_separation", 34)
	grid.add_theme_constant_override("v_separation", 2)
	lp.add_child(grid)
	for i in 4:
		grid.add_child(_label(String(VEHICLES[0]["spec"][i][0]), 11, F_MONO, MUTED))
	for i in 4:
		var v := _label("", 16, F_MONO, TEXT)
		grid.add_child(v)
		veh_spec.append(v)
	var rp := VBoxContainer.new()
	rp.anchor_right = 1.0
	rp.anchor_bottom = 1.0
	rp.offset_left = 640
	rp.offset_right = -56
	rp.offset_top = 40
	rp.offset_bottom = -40
	rp.add_theme_constant_override("separation", 6)
	dive.add_child(rp)
	var head := HBoxContainer.new()
	head.add_child(_label("ПОГРУЖЕНИЕ", 26, _vf(F_LOGO, 700), TEXT))
	var sp := Control.new()
	sp.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(sp)
	var esc := _label("Esc назад", 12, F_MONO, MUTED)
	esc.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	head.add_child(esc)
	rp.add_child(head)
	var gap := Control.new()
	gap.custom_minimum_size = Vector2(0, 8)
	rp.add_child(gap)
	rp.add_child(_label("СЦЕНА", 11, F_MONO, MUTED))
	for i in LEVELS.size():
		rp.add_child(_scene_row(i))
	var fill := Control.new()
	fill.size_flags_vertical = Control.SIZE_EXPAND_FILL
	rp.add_child(fill)
	start_btn = Button.new()
	start_btn.text = "НАЧАТЬ"
	start_btn.size_flags_horizontal = Control.SIZE_SHRINK_END
	start_btn.add_theme_font_override("font", _vf(F_SANS, 600))
	start_btn.add_theme_font_size_override("font_size", 17)
	for st in ["normal", "hover", "focus", "pressed", "disabled"]:
		var s := StyleBoxFlat.new()
		s.bg_color = AMBER if st != "disabled" else Color(AMBER, 0.25)
		if st == "hover" or st == "focus":
			s.bg_color = AMBER.lightened(0.15)
		s.set_corner_radius_all(4)
		s.content_margin_left = 40
		s.content_margin_right = 40
		s.content_margin_top = 13
		s.content_margin_bottom = 13
		start_btn.add_theme_stylebox_override(st, s)
	for c in ["font_color", "font_hover_color", "font_focus_color", "font_pressed_color"]:
		start_btn.add_theme_color_override(c, Color("140d06"))
	start_btn.add_theme_color_override("font_disabled_color", Color(0.08, 0.05, 0.02, 0.6))
	start_btn.pressed.connect(func(): _go(LEVELS[_scene]["id"]))
	rp.add_child(start_btn)


func _arrow(t: String, d: int) -> Button:
	var b := Button.new()
	b.text = t
	b.custom_minimum_size = Vector2(44, 44)
	b.add_theme_font_size_override("font_size", 22)
	b.add_theme_color_override("font_color", TEXT)
	for st in ["normal", "hover", "focus", "pressed"]:
		var s := StyleBoxFlat.new()
		s.draw_center = false
		s.set_border_width_all(1)
		s.border_color = AMBER if st != "normal" else Color(TEXT, 0.3)
		s.set_corner_radius_all(22)
		b.add_theme_stylebox_override(st, s)
	b.focus_mode = Control.FOCUS_NONE
	b.set_meta("sfx", "none")
	b.pressed.connect(_set_vehicle.bind(d))
	b.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	return b


func _scene_row(i: int) -> Button:
	var b := Button.new()
	b.custom_minimum_size = Vector2(0, 120)
	var sb := StyleBoxFlat.new()                   # выбранная сцена — янтарная рамка (_set_scene)
	sb.set_corner_radius_all(8)
	sb.set_border_width_all(1)
	for st in ["normal", "focus", "pressed"]:
		b.add_theme_stylebox_override(st, sb)
	row_style.append(sb)
	var hv := StyleBoxFlat.new()                   # под мышью — только светлая рамка, выбор не меняется
	hv.set_corner_radius_all(8)
	hv.set_border_width_all(1)
	hv.bg_color = Color(TEXT, 0.03)
	hv.border_color = Color(TEXT, 0.35)
	b.add_theme_stylebox_override("hover", hv)
	b.add_theme_stylebox_override("hover_pressed", hv)
	b.set_meta("hover_box", hv)
	var m := HBoxContainer.new()
	m.set_anchors_preset(Control.PRESET_FULL_RECT)
	m.offset_left = 12
	m.offset_right = -14
	m.offset_top = 12
	m.offset_bottom = -12
	m.add_theme_constant_override("separation", 16)
	m.mouse_filter = Control.MOUSE_FILTER_IGNORE
	b.add_child(m)
	var th := TextureRect.new()
	th.texture = LEVELS[i]["img"]
	th.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	th.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	th.custom_minimum_size = Vector2(168, 96)
	th.clip_contents = true
	th.mouse_filter = Control.MOUSE_FILTER_IGNORE
	m.add_child(th)
	var tv := VBoxContainer.new()
	tv.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	tv.alignment = BoxContainer.ALIGNMENT_CENTER
	tv.mouse_filter = Control.MOUSE_FILTER_IGNORE
	tv.add_child(_label(LEVELS[i]["title"], 20, _vf(F_SANS, 600), TEXT))
	var d := _label(LEVELS[i]["text"], 13, _vf(F_SANS, 400), Color("b8aa92"))
	d.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	tv.add_child(d)
	m.add_child(tv)
	var best := _label(_best(LEVELS[i]["id"]), 12, F_MONO, AMBER)
	best.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	m.add_child(best)
	for c in m.get_children() + tv.get_children():
		(c as Control).mouse_filter = Control.MOUSE_FILTER_IGNORE
	b.focus_entered.connect(_set_scene.bind(i))     # клавиатура: стрелки выбирают сцену
	b.pressed.connect(func():                        # щелчок / Enter: выбрать и перейти к «Начать» (запуск — только им)
		_set_scene(i)
		start_btn.grab_focus())
	rows.append(b)
	return b


func _set_scene(i: int) -> void:
	if i != _scene and dive.visible:
		UiSound.sfx("switch")
	_scene = i
	for k in rows.size():
		row_style[k].border_color = AMBER if k == i else Color(0, 0, 0, 0)
		row_style[k].bg_color = Color(AMBER, 0.07) if k == i else Color(0, 0, 0, 0)
		var hv: StyleBoxFlat = rows[k].get_meta("hover_box")
		hv.border_color = AMBER if k == i else Color(TEXT, 0.35)
		hv.bg_color = Color(AMBER, 0.1) if k == i else Color(TEXT, 0.03)


func _set_vehicle(d: int) -> void:
	_veh = posmod(_veh + d, VEHICLES.size())
	var v: Dictionary = VEHICLES[_veh]
	var empty := bool(v.get("empty", false))
	veh_idx.text = "АППАРАТ %d / %d" % [_veh + 1, VEHICLES.size()]
	veh_name.text = v["name"]
	veh_org.text = v["org"]
	veh_art.visible = not empty
	veh_empty.visible = empty
	for i in 4:
		veh_spec[i].text = v["spec"][i][1]
	start_btn.disabled = empty
	if d != 0:
		UiSound.sfx("switch")


func _open_dive() -> void:
	dive.visible = true
	_set_vehicle(0)
	_set_scene(_scene)
	rows[_scene].grab_focus()


func _close_dive() -> void:
	dive.visible = false
	items[0].grab_focus()


func _best(id: String) -> String:
	var mode := String(Settings.get_value("control"))
	var r: Array = []
	var key := ""
	if id == "pool":
		r = ResultsTable.load_rings("", mode)
		key = "total"
	elif id == "wreck":
		r = ResultsTable.load_wreck("", mode)
		key = "time"
	if key == "":
		return "без таблицы"
	if r.is_empty():
		return "—"
	return "%s с" % Hud.num(float(r[0][key]), 1)


func _go(scene: String) -> void:
	UiSound.menu_music(false)
	var lv: Dictionary = LEVELS[_scene]
	for l in LEVELS:                                 # --level: сцена по имени, не по выбранной строке
		if l["id"] == scene:
			lv = l
	Loading.go(get_tree(), scene, lv["title"], lv["img"])


func _input(ev: InputEvent) -> void:
	if splash:                                     # заставка забирает всё до кнопок (иначе Enter нажмёт пункт под ней)
		if ev.is_pressed() and _splash_t > SPLASH_SKIP:
			_end_splash()
		get_viewport().set_input_as_handled()
		return
	if not ev.is_pressed() or page_layer.visible:
		return
	if dive.visible and (ev.is_action("ui_left") or ev.is_action("ui_right")):
		_set_vehicle(-1 if ev.is_action("ui_left") else 1)
		get_viewport().set_input_as_handled()


func _unhandled_input(ev: InputEvent) -> void:
	if not ev.is_pressed():
		return
	var back := ev.is_action("ui_cancel") or ev.is_action("pause")
	if page_layer.visible:
		if back and not (get_viewport().gui_get_focus_owner() is OptionButton):
			UiSound.sfx("back")
			page_back.pressed.emit()                   # «назад» страницы: в меню или в настройки
			get_viewport().set_input_as_handled()
		return
	if dive.visible:
		if back:
			UiSound.sfx("back")
			_close_dive()
			get_viewport().set_input_as_handled()
		return
	if get_viewport().gui_get_focus_owner() == null:   # фокуса нет, пока не нажали клавишу или не навели мышь:
		if ev.is_action("ui_down") or ev.is_action("ui_up"):   # пункт не выглядит выбранным заранее
			items[0].grab_focus()
			get_viewport().set_input_as_handled()
		elif ev.is_action("ui_accept"):
			_open_dive()
			get_viewport().set_input_as_handled()


func _splash() -> void:
	splash = ColorRect.new()
	(splash as ColorRect).color = Color(0.02, 0.015, 0.01)
	splash.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(splash)
	var v := VBoxContainer.new()
	v.set_anchors_preset(Control.PRESET_FULL_RECT)
	v.alignment = BoxContainer.ALIGNMENT_CENTER
	v.add_theme_constant_override("separation", 12)
	splash.add_child(v)
	var lines := Credits.text().split("\n")
	for it in [["ROV-SIM", 44, _vf(F_LOGO, 700), TEXT], [lines[0].trim_prefix("ROV-Sim — "), 20, _vf(F_SANS, 400), TEXT],
			["аппарат «Петрович», кафедра МИСиТ СПбГМТУ", 14, F_MONO, MUTED]]:
		var l := _label(it[0], it[1], it[2], it[3])
		l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		v.add_child(l)
	_splash_t = 0.0


func _end_splash() -> void:
	var s := splash
	splash = null
	var tw := create_tween()
	tw.tween_property(s, "modulate:a", 0.0, 0.4)
	tw.tween_callback(s.queue_free)


## Страница на весь экран: заголовок Unbounded, «Esc назад» (кнопка), ниже содержимое шириной w.
func _page(title: String, w := 760.0, back := Callable()) -> VBoxContainer:
	for c in page_layer.get_children():
		if not (c is ColorRect):
			c.queue_free()
	page_layer.visible = true
	var head := HBoxContainer.new()
	head.anchor_right = 1.0
	head.offset_left = 80
	head.offset_right = -80
	head.offset_top = 40
	page_layer.add_child(head)
	page_title = _label(title, 26, _vf(F_LOGO, 700), TEXT)
	head.add_child(page_title)
	var sp := Control.new()
	sp.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(sp)
	page_back = Button.new()
	page_back.text = "Esc назад"
	page_back.add_theme_font_override("font", F_MONO)
	page_back.add_theme_font_size_override("font_size", 12)
	page_back.add_theme_color_override("font_color", MUTED)
	page_back.add_theme_color_override("font_hover_color", AMBER)
	for st in ["normal", "hover", "focus", "pressed"]:
		page_back.add_theme_stylebox_override(st, StyleBoxEmpty.new())
	page_back.focus_mode = Control.FOCUS_NONE
	page_back.set_meta("sfx", "back")
	page_back.pressed.connect(_close_page if back.is_null() else back)
	head.add_child(page_back)
	page_scroll = ScrollContainer.new()
	page_scroll.anchor_right = 1.0
	page_scroll.anchor_bottom = 1.0
	page_scroll.offset_left = 80
	page_scroll.offset_right = -80
	page_scroll.offset_top = 110
	page_scroll.offset_bottom = -40
	page_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	page_layer.add_child(page_scroll)
	page = VBoxContainer.new()
	page.custom_minimum_size = Vector2(w, 0)
	page.add_theme_constant_override("separation", 12)
	page_scroll.add_child(page)
	return page


## Первый элемент страницы под фокус (клавиатура и геймпад), Esc — назад.
func _focus_first(v: Node) -> void:
	for c in v.find_children("*", "BaseButton", true, false) + v.find_children("*", "LineEdit", true, false):
		(c as Control).grab_focus.call_deferred()
		return


func _close_page() -> void:
	page_layer.visible = false
	for c in page_layer.get_children():
		if not (c is ColorRect):
			c.queue_free()
	_update_foot()
	items[0].grab_focus()


func _results(rings: bool) -> void:
	var v := _page("РЕЗУЛЬТАТЫ", 1100)
	var tabs := HBoxContainer.new()
	tabs.add_theme_constant_override("separation", 8)
	var b1 := MenuKit.button(tabs, "Кольца", _results.bind(true))
	var b2 := MenuKit.button(tabs, "Судно", _results.bind(false))
	(b1 if rings else b2).add_theme_color_override("font_color", AMBER)
	v.add_child(tabs)
	var t := ResultsTable.new()
	t.set_plain()
	var mode := String(Settings.get_value("control"))
	var ft := "режим: %s (настройки) · CSV: " % Settings.MODES.get(mode, mode)
	if rings:
		t.show_rings(ResultsTable.load_rings("", mode), {}, ft + Paths.shown(Paths.file("rings_results.csv")))
	else:
		t.show_wreck(ResultsTable.load_wreck("", mode), {}, ft + Paths.shown(Paths.file("wreck_results.csv")))
	v.add_child(t)
	(b1 if rings else b2).grab_focus.call_deferred()


## Настройки: имя пилота, звук, режим управления, графика (MenuKit.settings_box). Справка по клавишам — F1 в сцене.
func _settings() -> void:
	var v := _page("НАСТРОЙКИ", 820)
	MenuKit.heading(v, "ПИЛОТ", 12)
	var ne := LineEdit.new()
	ne.text = String(Settings.get_value("player"))
	ne.max_length = 20
	ne.custom_minimum_size = Vector2(300, 0)
	ne.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	ne.text_changed.connect(func(t): Settings.set_value("player", t.strip_edges() if t.strip_edges() != "" else "игрок"))
	v.add_child(ne)
	var gap := Control.new()
	gap.custom_minimum_size = Vector2(0, 6)
	v.add_child(gap)
	v.add_child(MenuKit.settings_box(func(): pass))
	_focus_first(v)


func _about() -> void:
	var v := _page("КАК ЭТО РАБОТАЕТ", 820, _authors)
	for s in [
		["АППАРАТ", "«Петрович» — макет кафедры МИСиТ СПбГМТУ: корпус Ø110/140 × 650 мм, 8,2 кг, два маршевых движителя и две поршневые цистерны по 70 мл. Глубину меняют цистерны, крен и боковое смещение не управляются."],
		["ДВИЖЕНИЕ", "Уравнения Fossen с 6 степенями свободы: присоединённые массы, сопротивление по силуэтам модели, плавучесть, тяга. Тот же расчёт есть на Python, совпадение до 0,0002 мм."],
		["СВЕТ", "Поглощение по R, G, B (Pope & Fry), отдельно обратное рассеяние от лампы. Проверено по кадрам мишени Холопова и статье Игнатьевой и Кузьменко."],
		["КАМЕРА", "Объектив DiCam 300 (140° на воздухе) за плоским окном бокса: в воде ≈ 90°. Снимок бокового обзора в меню — рельеф места судна из Blender при низком боковом свете, не запись прибора."],
		["ИСТОЧНИКИ", "У каждого числа есть источник и статус «проверено / подогнано / оценка»: docs/physics-sources.md и docs/verification-report.md."]]:
		MenuKit.heading(v, s[0], 12)
		MenuKit.note(v, s[1])


func _authors() -> void:
	var v := _page("АВТОРЫ", 900)
	var lines := Credits.text().split("
")
	MenuKit.heading(v, "ROV-SIM", 12)
	v.add_child(_label(lines[0].trim_prefix("ROV-Sim — "), 22, _vf(F_SANS, 600), TEXT))
	MenuKit.heading(v, "АППАРАТ «ПЕТРОВИЧ»", 12)
	MenuKit.note(v, lines[1].trim_prefix("Аппарат «Петрович» — "))
	var names := ""
	for i in range(2, lines.size() - 1):
		names += lines[i] + "
"
	v.add_child(_label(names.strip_edges(), 17, _vf(F_SANS, 500), TEXT))
	MenuKit.heading(v, "ПЕРВАЯ ВЕРСИЯ СИМУЛЯТОРА", 12)
	v.add_child(_label(lines[lines.size() - 1].trim_prefix("Первая версия симулятора — "), 17, _vf(F_SANS, 500), TEXT))
	MenuKit.heading(v, "ИСТОЧНИКИ И ЧУЖИЕ МАТЕРИАЛЫ", 12)
	MenuKit.note(v, "Проверка света: статья Игнатьевой Н. В. и Кузьменко А. В., 2024. Физика: Fossen, Pope и Fry, Mobley и др.
" +
			"Судно: «Malpas Metal Boat Wreck», artfletch, CC BY 4.0. Текстуры Poly Haven (CC0).
" +
			"Шрифты PT Mono, PT Sans, Unbounded, IBM Plex (OFL). Звуки Kenney и музыка «Aquaria» (CC0).
" +
			"Движок Godot Engine (MIT). Полный список и лицензии: папка licenses рядом с ROV-Sim.exe.")
	MenuKit.button(v, "Как это работает", _about)
