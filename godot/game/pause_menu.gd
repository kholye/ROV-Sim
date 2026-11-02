class_name PauseMenu
extends CanvasLayer
## Пауза (Esc / Start): продолжить, заново, ПИД, настройки, управление, главное меню, выход.
## Физика стоит, пока открыто меню. link_lost: связь с аппаратом потеряна — только «заново» или меню.

var level: LevelBase
var box: CenterContainer
var body: VBoxContainer
var locked := false                # связь потеряна: Esc не продолжает


func setup(lvl: LevelBase) -> void:
	level = lvl
	layer = 10
	process_mode = Node.PROCESS_MODE_ALWAYS
	var dim := ColorRect.new()
	dim.color = Color(0, 0, 0, 0.55)
	dim.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(dim)
	box = CenterContainer.new()
	box.set_anchors_preset(Control.PRESET_FULL_RECT)
	box.theme = MenuKit.theme()
	add_child(box)
	visible = false


func open() -> void:
	visible = true
	get_tree().paused = true
	_main()


func close() -> void:
	visible = false
	get_tree().paused = false
	level.apply_settings()


func _page() -> VBoxContainer:
	for c in box.get_children():
		c.queue_free()
	var p := MenuKit.panel(620)
	box.add_child(p)
	body = VBoxContainer.new()
	body.add_theme_constant_override("separation", 8)
	p.add_child(body)
	return body


func _main() -> void:
	var v := _page()
	MenuKit.heading(v, "ПАУЗА", 26)
	var first := MenuKit.button(v, "Продолжить", close)
	MenuKit.button(v, "Заново", func(): get_tree().paused = false; get_tree().reload_current_scene())
	MenuKit.button(v, "ПИД глубины", _pid)
	MenuKit.button(v, "Настройки", _settings)
	MenuKit.button(v, "Управление", func(): close(); level.hud.help.visible = true)
	MenuKit.button(v, "Главное меню", func(): get_tree().paused = false; get_tree().change_scene_to_file(MenuKit.SCENES["menu"]))
	MenuKit.button(v, "Выход", func(): get_tree().quit())
	first.grab_focus.call_deferred()


func link_lost(text: String) -> void:
	locked = true
	visible = true
	get_tree().paused = not level.args.has("shot")      # снимок (--shot) делается в работающем дереве
	var v := _page()
	MenuKit.heading(v, "СВЯЗЬ ПОТЕРЯНА", 26)
	MenuKit.note(v, text)
	var first := MenuKit.button(v, "Начать заново", func(): get_tree().paused = false; get_tree().reload_current_scene())
	MenuKit.button(v, "Главное меню", func(): get_tree().paused = false; get_tree().change_scene_to_file(MenuKit.SCENES["menu"]))
	first.grab_focus.call_deferred()


func _pid() -> void:
	var v := _page()
	v.add_child(MenuKit.pid_box(level.rov))
	MenuKit.button(v, "← Назад", _main).grab_focus.call_deferred()


func _settings() -> void:
	var v := _page()
	v.add_child(MenuKit.settings_box(func(): pass))
	MenuKit.button(v, "← Назад", _main).grab_focus.call_deferred()


func _unhandled_input(ev: InputEvent) -> void:
	if ev.is_action("pause") and ev.is_pressed() and not ev.is_echo():
		if locked:
			pass
		elif visible:
			close()
		else:
			open()
		get_viewport().set_input_as_handled()
