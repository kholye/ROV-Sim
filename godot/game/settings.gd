class_name Settings
extends RefCounted
## Настройки игрока: user://settings.cfg (на Windows %APPDATA%\Godot\app_userdata\ROV-Sim\).
## Только вид и интерфейс; физика и свет здесь не настраиваются.

const PATH := "user://settings.cfg"
const DEFAULTS := {
	"filters": false,         # стильный вид (Tab, настройки); выкл = научный: только расчёт света и интерфейс
	"control": "science",     # режим управления: science / assist / boost (MODES), с следующего запуска уровня
	"pip": true,              # окошко «со стороны» (V)
	"pip_cam": 0,             # 0 сбоку, 1 сзади, 2 сверху (Shift+V)
	"forces": true,           # векторы сил в окошке (F3)
	"graph": false,           # график глубины (F2)
	"light_curve": false,     # кривая ослабления света (F4)
	"style_scale": 3,         # стильный вид: 3D считается в 1/N разрешения (2 или 3)
	"volume": 0.8,
	"vsync": true,
	"show_fps": false,
	"player": "игрок",
	"pid": [0.2, 5.1, 0.0],   # Kp, Kd, Ki в шкале пульта 0,0-9,9 (порядок команды n); по V3
}

## Режимы управления (game/rov.gd): научный — как пульт; автопилот — та же физика, помогает пульт;
## автопилот + ускорение — ещё насос цистерн ×3 и тяга ×1,5 (уже не настоящий аппарат).
const MODES := {"science": "научный", "assist": "автопилот", "boost": "автопилот + ускорение"}
const VERSION := 2               # 2: стильный вид по умолчанию выключен (сохранённое «включено» сбрасывается)

static var _cfg: ConfigFile
static var _over := {}           # из командной строки (снимки, замеры): не сохраняются


static func _load() -> void:
	if _cfg != null:
		return
	_cfg = ConfigFile.new()
	_cfg.load(PATH)
	if int(_cfg.get_value("main", "version", 1)) < VERSION:
		if _cfg.has_section_key("main", "filters"):
			_cfg.erase_section_key("main", "filters")
		_cfg.set_value("main", "version", VERSION)
		_cfg.save(PATH)


static func get_value(key: String):
	if _over.has(key):
		return _over[key]
	_load()
	return _cfg.get_value("main", key, DEFAULTS[key])


## Аргументы «--filters 0», «--pip 1», «--style_scale 2» и т. п. на один запуск, без записи в файл.
static func override_from_args(args: Dictionary) -> void:
	for k in args:
		if DEFAULTS.has(k) and not (DEFAULTS[k] is Array):
			var d = DEFAULTS[k]
			var s := String(args[k]) if not (args[k] is bool) else "1"
			_over[k] = (s != "0" and s != "false") if d is bool else (int(s) if d is int else (float(s) if d is float else s))


static func set_value(key: String, v) -> void:
	_load()
	_cfg.set_value("main", key, v)
	_cfg.save(PATH)


static func toggle(key: String) -> bool:
	var v := not bool(get_value(key))
	set_value(key, v)
	return v


## Применить то, что действует на всё окно (синхронизация, громкость).
static func apply_global() -> void:
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_ENABLED if get_value("vsync") else DisplayServer.VSYNC_DISABLED)
	AudioServer.set_bus_volume_db(0, linear_to_db(maxf(float(get_value("volume")), 0.0001)))
