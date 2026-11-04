class_name Settings
extends RefCounted
## Настройки игрока: settings.cfg в папке данных (Paths: у .exe — userdata рядом с игрой).
## Только вид и интерфейс; физика и свет здесь не настраиваются.

const FILE := "settings.cfg"
const DEFAULTS := {
	"control": "science",     # режим управления: science / assist / boost (MODES), с следующего запуска уровня
	"pip": true,              # окошко «со стороны» (V)
	"pip_cam": 0,             # 0 сбоку, 1 сзади, 2 сверху (Shift+V)
	"forces": true,           # векторы сил в окошке (F3)
	"graph": false,           # график глубины (F2)
	"light_curve": false,     # кривая ослабления света (F4)
	"render_scale": 1.0,      # доля разрешения 3D (графика): 1 / 0,75 / 0,5 — на слабой видеокарте быстрее
	"volume": 0.8,            # громкость: общая, музыка меню, звуки (интерфейс, аппарат и место)
	"volume_music": 1.0,
	"volume_sfx": 1.0,
	"cam_tilt": 20.0,         # наклон камеры аппарата вниз, ° (I / K в сцене; оценка, docs/ui.md)
	"vsync": true,
	"show_fps": false,
	"player": "игрок",
	"pid": [0.2, 5.1, 0.0],   # Kp, Kd, Ki в шкале пульта 0,0-9,9 (порядок команды n); по V3
}

## Режимы управления (game/rov.gd): научный — как пульт; автопилот — та же физика, помогает пульт;
## автопилот + ускорение — ещё насос цистерн ×3 и тяга ×1,5 (уже не настоящий аппарат).
const MODES := {"science": "научный", "assist": "автопилот", "boost": "автопилот + ускорение"}
const VERSION := 3               # 3: стильного вида больше нет (ключи filters, style_scale удаляются)

static var _cfg: ConfigFile
static var _over := {}           # из командной строки (снимки, замеры): не сохраняются


static func _load() -> void:
	if _cfg != null:
		return
	_cfg = ConfigFile.new()
	_cfg.load(Paths.file(FILE))
	if int(_cfg.get_value("main", "version", 1)) < VERSION:
		for k in ["filters", "style_scale"]:
			if _cfg.has_section_key("main", k):
				_cfg.erase_section_key("main", k)
		_cfg.set_value("main", "version", VERSION)
		_cfg.save(Paths.file(FILE))


static func get_value(key: String):
	if _over.has(key):
		return _over[key]
	_load()
	return _cfg.get_value("main", key, DEFAULTS[key])


## Аргументы «--pip 1», «--render_scale 0.5» и т. п. на один запуск, без записи в файл.
static func override_from_args(args: Dictionary) -> void:
	for k in args:
		if DEFAULTS.has(k) and not (DEFAULTS[k] is Array):
			var d = DEFAULTS[k]
			var s := String(args[k]) if not (args[k] is bool) else "1"
			_over[k] = (s != "0" and s != "false") if d is bool else (int(s) if d is int else (float(s) if d is float else s))


static func set_value(key: String, v) -> void:
	_load()
	_cfg.set_value("main", key, v)
	_cfg.save(Paths.file(FILE))


static func toggle(key: String) -> bool:
	var v := not bool(get_value(key))
	set_value(key, v)
	return v


## Применить то, что действует на всё окно (синхронизация, громкость).
static func apply_global() -> void:
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_ENABLED if get_value("vsync") else DisplayServer.VSYNC_DISABLED)
	AudioServer.set_bus_volume_db(0, linear_to_db(maxf(float(get_value("volume")), 0.0001)))
	for b in [["Music", "volume_music"], ["UI", "volume_sfx"], ["World", "volume_sfx"]]:
		var i := AudioServer.get_bus_index(b[0])
		if i >= 0:
			AudioServer.set_bus_volume_db(i, linear_to_db(maxf(float(get_value(b[1])), 0.0001)))
