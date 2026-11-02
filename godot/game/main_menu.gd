extends Control
## Главное меню: выбор сцены, имя игрока, таблица результатов, настройки, управление, «как это работает».
## Фон — кадр из игры (у судна, вид сзади) через тот же стиль, что и в игре.

const BG := preload("res://assets/ui/menu_bg.png")

static var _level_done := false
var page: VBoxContainer
var side: CenterContainer


func _ready() -> void:
	var a := OS.get_cmdline_user_args()
	var lv := a.find("--level")                   # --level pool / wreck / lab: сразу в сцену (сборка .exe
	if lv >= 0 and lv + 1 < a.size() and not _level_done:   # не принимает путь сцены); остальные аргументы читает уровень
		_level_done = true                          # «Главное меню» из паузы потом открывает меню
		_go.call_deferred(a[lv + 1])
		return
	Settings.apply_global()
	PultInput.ensure_actions()
	theme = MenuKit.theme()
	var bg := TextureRect.new()
	bg.texture = BG
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	bg.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	bg.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	bg.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	if Settings.get_value("filters"):
		bg.material = StylePass.material_for(Vector2(427, 240))
	add_child(bg)
	var shade := ColorRect.new()
	shade.color = Color(0, 0, 0, 0.35)
	shade.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(shade)
	var left := VBoxContainer.new()
	left.position = Vector2(64, 56)
	left.custom_minimum_size = Vector2(410, 0)
	left.add_theme_constant_override("separation", 8)
	add_child(left)
	var title := Label.new()
	title.text = "ROV-SIM"
	title.add_theme_font_size_override("font_size", 64)
	title.add_theme_color_override("font_color", Hud.WHITE)
	left.add_child(title)
	var ver := Label.new()                         # версия из project.godot (application/config/version)
	ver.text = "версия " + str(ProjectSettings.get_setting("application/config/version", ""))
	ver.add_theme_color_override("font_color", Color(Hud.WHITE, 0.6))
	left.add_child(ver)
	MenuKit.note(left, "Симулятор подводного аппарата СПбГМТУ: 2 движителя, 2 цистерны по 70 мл.\n" +
			"Физика по Fossen, свет по каналам R/G/B, у каждого числа — источник.")
	var name_row := HBoxContainer.new()
	var nl := Label.new()
	nl.text = "Пилот  "
	name_row.add_child(nl)
	var ne := LineEdit.new()
	ne.text = String(Settings.get_value("player"))
	ne.max_length = 20
	ne.custom_minimum_size = Vector2(240, 0)
	ne.text_changed.connect(func(t): Settings.set_value("player", t.strip_edges() if t.strip_edges() != "" else "игрок"))
	name_row.add_child(ne)
	left.add_child(name_row)
	var gap := Control.new()
	gap.custom_minimum_size = Vector2(0, 8)
	left.add_child(gap)
	var first := MenuKit.button(left, "Бассейн с кольцами", func(): _go("pool"))
	MenuKit.button(left, "Затонувшее судно", func(): _go("wreck"))
	MenuKit.button(left, "Лаб. бассейн 3×3×3 (проверки)", func(): _go("lab"))
	MenuKit.button(left, "Таблица результатов", _results.bind(true))
	MenuKit.button(left, "Настройки", _settings)
	MenuKit.button(left, "Управление", _controls)
	MenuKit.button(left, "Как это работает", _about)
	MenuKit.button(left, "Выход", func(): get_tree().quit())
	first.grab_focus.call_deferred()
	side = CenterContainer.new()
	side.anchor_left = 0.385
	side.offset_right = -24
	side.anchor_right = 1.0
	side.anchor_bottom = 1.0
	add_child(side)
	var foot := Label.new()
	foot.text = "Аппарат и опыты: Холопов, Дунаев (СПбГМТУ, 2026) · свет: Игнатьева и Кузьменко (2024) · " + \
			"судно: «Malpas Metal Boat Wreck», artfletch, CC BY 4.0 · шрифт PT Mono (OFL)"
	foot.add_theme_font_size_override("font_size", 12)
	foot.add_theme_color_override("font_color", Color(Hud.WHITE, 0.6))
	foot.anchor_top = 1.0
	foot.anchor_bottom = 1.0
	foot.offset_left = 24
	foot.offset_top = -28
	add_child(foot)
	_results(true)
	var k := a.find("--shot")                      # --shot <png>: снимок меню для docs/
	if k >= 0 and k + 1 < a.size():
		for i in 20:
			await get_tree().process_frame
		get_viewport().get_texture().get_image().save_png(a[k + 1])
		get_tree().quit()


func _go(scene: String) -> void:
	get_tree().change_scene_to_file(MenuKit.SCENES[scene])


func _page(w := 700.0) -> VBoxContainer:
	for c in side.get_children():
		c.queue_free()
	var p := MenuKit.panel(w)
	side.add_child(p)
	page = VBoxContainer.new()
	page.add_theme_constant_override("separation", 10)
	p.add_child(page)
	return page


func _results(rings: bool) -> void:
	var v := _page(0)
	var tabs := HBoxContainer.new()
	tabs.add_theme_constant_override("separation", 8)
	MenuKit.button(tabs, "Кольца", _results.bind(true))
	MenuKit.button(tabs, "Судно", _results.bind(false))
	v.add_child(tabs)
	var t := ResultsTable.new()
	var mode := String(Settings.get_value("control"))
	var foot := "Режим: %s (настройки) · CSV: " % Settings.MODES.get(mode, mode)
	if rings:
		t.show_rings(ResultsTable.load_rings("user://", mode), {}, foot + ProjectSettings.globalize_path("user://rings_results.csv"))
	else:
		t.show_wreck(ResultsTable.load_wreck("user://", mode), {}, foot + ProjectSettings.globalize_path("user://wreck_results.csv"))
	v.add_child(t)


func _settings() -> void:
	var v := _page()
	v.add_child(MenuKit.settings_box(func(): pass))


func _controls() -> void:
	var v := _page(900)
	var r := RichTextLabel.new()
	r.bbcode_enabled = true
	r.fit_content = true
	r.add_theme_font_size_override("normal_font_size", 15)
	r.text = Hud.HELP
	v.add_child(r)


func _about() -> void:
	var v := _page(760)
	MenuKit.heading(v, "КАК ЭТО РАБОТАЕТ")
	for s in [
		"Аппарат — настоящий ТНПА кафедры: корпус Ø110/140 × 650 мм, 8,2 кг, два маршевых движителя и две поршневые цистерны по 70 мл. Глубину меняют цистерны, крен и боковое смещение не управляются.",
		"Движение — уравнения Fossen с 6 степенями свободы: присоединённые массы, сопротивление по силуэтам модели, плавучесть, тяга. Тот же расчёт есть на Python, совпадение до 0,0002 мм.",
		"Свет — поглощение по R, G, B (Pope & Fry), отдельно обратное рассеяние от лампы. Проверено по кадрам мишени Холопова и статье Игнатьевой и Кузьменко.",
		"Стильный вид (Tab) — только последний проход поверх готового кадра. Научный вид показывает чистый расчёт.",
		"У каждого числа есть источник и статус «проверено / подогнано / оценка»: docs/physics-sources.md и docs/verification-report.md."]:
		MenuKit.note(v, "· " + s)
