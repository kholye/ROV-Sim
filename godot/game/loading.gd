class_name Loading
extends CanvasLayer
## Экран загрузки сцены (версия 1.4) в стиле меню (MenuKit: тёмный фон, янтарный акцент, Unbounded / IBM Plex).
## Три этапа: ресурсы сцены грузятся в фоновом потоке (ResourceLoader.load_threaded_request) — полоса идёт по
## прогрессу загрузчика; сборка сцены (_ready уровня: столкновения, обрастание, кабель) — на главном потоке,
## экран в это время стоит на месте; прогрев — первые кадры, пока видеокарта компилирует шейдеры: дерево на
## паузе (аппарат стоит), экран сверху, пока кадры не станут ровными. Затем экран плавно гаснет.
## Ввод во время загрузки забирается целиком (Esc не откроет паузу под экраном).

const WARM_MIN := 12               # кадров прогрева не меньше
const WARM_MAX := 6.0              # с: прогрев не дольше
const WARM_OK_MS := 40.0           # кадр короче — «ровный»; нужно WARM_STEADY подряд
const WARM_STEADY := 8
const FADE := 0.35

var path := ""
var title := ""
var img: Texture2D
var _bar: ColorRect
var _bar_bg: ColorRect
var _pct: Label
var _stage: Label
var _root: Control
var _phase := 0                    # 0 ресурсы, 1 сборка, 2 прогрев, 3 гаснет
var _shown := 0.0                  # показанная доля (плавно догоняет настоящую)
var _want := 0.0
var _warm_n := 0
var _warm_t := 0.0
var _steady := 0
var _fade := 0.0
var _t := 0.0
var _level: Node


## Уйти из текущей сцены в сцену id (MenuKit.SCENES) через экран загрузки.
static func go(tree: SceneTree, id: String, title_: String, img_: Texture2D = null) -> void:
	var l := Loading.new()
	l.name = "Loading"
	l.path = MenuKit.SCENES[id]
	l.title = title_
	l.img = img_
	tree.root.add_child(l)
	if tree.current_scene:
		tree.current_scene.queue_free()
	ResourceLoader.load_threaded_request(l.path, "PackedScene", true)


func _ready() -> void:
	layer = 50
	process_mode = Node.PROCESS_MODE_ALWAYS
	_root = Control.new()
	_root.set_anchors_preset(Control.PRESET_FULL_RECT)
	_root.mouse_filter = Control.MOUSE_FILTER_STOP
	add_child(_root)
	var bg := ColorRect.new()
	bg.color = MenuKit.BG
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	_root.add_child(bg)
	if img:                                         # кадр сцены справа, затухает к тексту
		var pic := TextureRect.new()
		pic.texture = img
		pic.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		pic.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
		pic.anchor_left = 0.42
		pic.anchor_right = 1.0
		pic.anchor_bottom = 1.0
		pic.modulate = Color(1, 1, 1, 0.55)
		_root.add_child(pic)
		var fade := TextureRect.new()
		var g := Gradient.new()
		g.colors = PackedColorArray([MenuKit.BG, Color(MenuKit.BG, 0.0)])
		var gt := GradientTexture2D.new()
		gt.gradient = g
		gt.fill_from = Vector2(0, 0)
		gt.fill_to = Vector2(1, 0)
		fade.texture = gt
		fade.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		fade.anchor_left = 0.42
		fade.anchor_right = 0.75
		fade.anchor_bottom = 1.0
		_root.add_child(fade)
	var col := VBoxContainer.new()
	col.anchor_top = 1.0
	col.anchor_bottom = 1.0
	col.offset_left = 72
	col.offset_top = -300
	col.offset_right = 640
	col.offset_bottom = -88
	col.add_theme_constant_override("separation", 10)
	_root.add_child(col)
	col.add_child(_label("ПОГРУЖЕНИЕ", 12, MenuKit.vf(MenuKit.F_MONO), MenuKit.MUTED))
	var t := _label(title.to_upper(), 34, MenuKit.vf(MenuKit.F_LOGO, 700), MenuKit.TEXT)
	t.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	col.add_child(t)
	var gap := Control.new()
	gap.custom_minimum_size = Vector2(0, 18)
	col.add_child(gap)
	var bar_box := Control.new()
	bar_box.custom_minimum_size = Vector2(0, 2)
	col.add_child(bar_box)
	_bar_bg = ColorRect.new()
	_bar_bg.color = Color(MenuKit.TEXT, 0.12)
	_bar_bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	bar_box.add_child(_bar_bg)
	_bar = ColorRect.new()
	_bar.color = MenuKit.AMBER
	_bar.anchor_bottom = 1.0
	bar_box.add_child(_bar)
	var row := HBoxContainer.new()
	_stage = _label("", 13, MenuKit.vf(MenuKit.F_MONO), MenuKit.SOFT)
	_stage.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(_stage)
	_pct = _label("0 %", 13, MenuKit.vf(MenuKit.F_MONO), MenuKit.AMBER)
	row.add_child(_pct)
	col.add_child(row)
	var hint := _label("F1 — управление   Esc — пауза", 12, MenuKit.vf(MenuKit.F_MONO), MenuKit.MUTED)
	hint.anchor_top = 1.0
	hint.anchor_bottom = 1.0
	hint.offset_left = 72
	hint.offset_top = -48
	_root.add_child(hint)
	_set_stage("загрузка моделей и текстур")


func _label(text: String, size: int, font: Font, color: Color) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_override("font", font)
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)
	return l


func _set_stage(s: String) -> void:
	_stage.text = s


func _input(_ev: InputEvent) -> void:
	get_viewport().set_input_as_handled()


func _process(dt: float) -> void:
	_t += dt
	match _phase:
		0:
			var pr := []
			var st := ResourceLoader.load_threaded_get_status(path, pr)
			if st == ResourceLoader.THREAD_LOAD_IN_PROGRESS:
				_want = 0.75 * float(pr[0]) if pr.size() > 0 else _want
			elif st == ResourceLoader.THREAD_LOAD_LOADED:
				_want = 0.75
				if _shown > 0.7:                       # полоса догнала: следующим кадром сборка
					_phase = 1
					_set_stage("сборка сцены")
			else:
				push_error("загрузка не удалась: " + path)
				_phase = -1
		1:
			if _shown >= 0.74:                         # кадр с «сборка сцены» уже нарисован
				var ps := ResourceLoader.load_threaded_get(path) as PackedScene
				get_tree().paused = true                # аппарат не двигается, пока экран сверху
				_level = ps.instantiate()
				get_tree().root.add_child(_level)       # _ready уровня — здесь (главный поток)
				get_tree().current_scene = _level
				_phase = 2
				_want = 0.9
				_set_stage("подготовка шейдеров")
		2:
			_warm_n += 1
			_warm_t += dt
			_steady = _steady + 1 if dt * 1000.0 < WARM_OK_MS else 0
			_want = 0.9 + 0.1 * clampf(float(_warm_n) / WARM_MIN, 0.0, 1.0)
			if (_warm_n >= WARM_MIN and _steady >= WARM_STEADY) or _warm_t > WARM_MAX:
				_phase = 3
				_want = 1.0
				get_tree().paused = false
		3:
			_fade += dt
			_root.modulate.a = 1.0 - clampf(_fade / FADE, 0.0, 1.0)
			if _fade >= FADE:
				queue_free()
	_shown = move_toward(_shown, _want, dt * 2.5) if _phase < 2 else _want
	_bar.anchor_right = _shown
	_pct.text = "%d %%" % roundi(_shown * 100.0)
